"""Token-only registry publication of previously verified immutable artifacts.

Writes are guarded to this repository's explicitly authorized release workflow.
Dry-run code uses public GETs only. Tokens never appear in argv or state files.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from release_support import IMAGE, REPOSITORY, ROOT, publication_order, sha, version


class ReleaseError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a registry credential to a redirect target.
        return None


def request(url, *, method="GET", data=None, headers=None, missing=False):
    req = Request(
        url,
        data=data,
        method=method,
        headers={
            "User-Agent": "LeakScope-release/1 (https://github.com/polsala/LeakScope)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    try:
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            raw = response.read(8 * 1024**2 + 1)
            if len(raw) > 8 * 1024**2:
                raise ReleaseError("Registry response exceeds limit")
            return raw, {k.lower(): v for k, v in response.headers.items()}
    except HTTPError as error:
        if error.code == 404 and missing:
            return None, {}
        # Do not echo server bodies: they may contain credentials or unsafe text.
        raise ReleaseError(
            f"Registry HTTP {error.code} at {req.host}: authorization/name/scope conflicts require review; writes are never retried automatically"
        ) from None


def get(url, *, missing=False, headers=None):
    raw, unused = request(url, missing=missing, headers=headers)
    return None if raw is None else json.loads(raw)


def wait_for(check, *, timeout=180):
    deadline = time.monotonic() + timeout
    delay = 1
    while True:
        result = check()
        if result:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReleaseError(
                "Registry propagation deadline exceeded; rerun the failed job to inspect existing immutable versions"
            )
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, 15)


def authorized(component):
    expected = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": REPOSITORY,
        "RELEASE_PUBLICATION_AUTHORIZED": "yes",
    }
    if any(os.getenv(k) != v for k, v in expected.items()) or os.getenv(
        "GITHUB_EVENT_NAME"
    ) not in {"push", "workflow_dispatch"}:
        raise ReleaseError(
            "Publication is only permitted in the explicitly authorized release workflow; local/dry runs cannot upload"
        )
    workflow = os.getenv("GITHUB_WORKFLOW_REF", "")
    if not workflow.startswith(REPOSITORY + "/.github/workflows/release.yml@"):
        raise ReleaseError("Unexpected publishing workflow identity")
    required = {
        "crates": "CARGO_REGISTRY_TOKEN",
        "pypi": "TWINE_PASSWORD",
        "ghcr": "GH_TOKEN",
        "draft": "GH_TOKEN",
        "finalize": "GH_TOKEN",
    }[component]
    if not os.getenv(required):
        raise ReleaseError("Missing required publication credential: " + required)
    if component == "pypi" and os.getenv("TWINE_USERNAME") != "__token__":
        raise ReleaseError("PyPI requires token authentication with TWINE_USERNAME=__token__")


def cargo_metadata(path, commit):
    with tarfile.open(path, "r:gz") as archive:
        prefix = path.name[:-6] + "/"

        def read(name):
            f = archive.extractfile(prefix + name)
            if f is None:
                raise ReleaseError("Missing Cargo package resource")
            return f.read()

        vcs = json.loads(read(".cargo_vcs_info.json"))
        assert vcs["git"]["sha1"] == commit and not vcs["git"].get("dirty"), (
            "Cargo package source identity mismatch"
        )
        doc = tomllib.loads(read("Cargo.toml").decode())
        p = doc["package"]
        deps = []

        def add(tables, target=None):
            for kind, label in [
                ("dependencies", "normal"),
                ("dev-dependencies", "dev"),
                ("build-dependencies", "build"),
            ]:
                for alias, dep in tables.get(kind, {}).items():
                    if isinstance(dep, str):
                        dep = {"version": dep}
                    assert "path" not in dep, "Registry package contains a path dependency"
                    deps.append(
                        {
                            "name": dep.get("package", alias),
                            "version_req": dep["version"],
                            "features": dep.get("features", []),
                            "optional": dep.get("optional", False),
                            "default_features": dep.get("default-features", True),
                            "target": target,
                            "kind": label,
                            "registry": None,
                            "explicit_name_in_toml": alias if "package" in dep else None,
                        }
                    )

        add(doc)
        for target, table in doc.get("target", {}).items():
            add(table, target)
        return {
            "name": p["name"],
            "vers": p["version"],
            "deps": deps,
            "features": doc.get("features", {}),
            "authors": p.get("authors", []),
            "description": p["description"],
            "documentation": p.get("documentation"),
            "homepage": p["homepage"],
            "readme": read(p["readme"]).decode(),
            "readme_file": p["readme"],
            "keywords": p["keywords"],
            "categories": p.get("categories", []),
            "license": p["license"],
            "license_file": p.get("license-file"),
            "repository": p["repository"],
            "links": p.get("links"),
            "rust_version": p["rust-version"],
        }


def crate_status(item, digest, *, owner=None):
    name, number = item["name"], item["vers"]
    project = get("https://crates.io/api/v1/crates/" + name, missing=True)
    if project is None:
        return "first_publication"
    crate = project["crate"]
    if (
        crate["name"] != name
        or crate.get("repository", "").rstrip("/") != "https://github.com/" + REPOSITORY
    ):
        raise ReleaseError("Crate name collision or source repository mismatch: " + name)
    if owner:
        owners = get(f"https://crates.io/api/v1/crates/{name}/owners")["users"]
        if owner not in {u["login"] for u in owners}:
            raise ReleaseError(
                "Crate ownership conflict: "
                + name
                + "; expected direct registry owner "
                + owner
                + ". Team-only ownership requires explicit reconciliation."
            )
    existing = get(f"https://crates.io/api/v1/crates/{name}/{number}", missing=True)
    if existing is None:
        return "new_version"
    v = existing["version"]
    if v["num"] != number or v["checksum"] != digest or v.get("yanked"):
        raise ReleaseError("Immutable crate version conflicts with intended release: " + name)
    return "verified_existing"


def crate_index(item, digest):
    name = item["name"]
    path = name[:2] + "/" + name[2:4] + "/" + name
    raw, unused = request("https://index.crates.io/" + path, missing=True)
    if raw is None:
        return False
    for line in raw.splitlines():
        row = json.loads(line)
        if row["vers"] == item["vers"]:
            if row["cksum"] != digest or row.get("yanked"):
                raise ReleaseError("Registry index checksum/yank conflict: " + name)
            return True
    return False


def publish_crates(directory, manifest):
    authorized("crates")
    token = os.environ["CARGO_REGISTRY_TOKEN"]
    metadata = json.loads((directory / "cargo-publish.json").read_text())
    assert [p["name"] for p in metadata] == publication_order()
    owner = os.getenv("CRATES_IO_OWNER", "polsala")
    statuses = {
        p["name"]: crate_status(
            p, manifest["assets"][f"{p['name']}-{p['vers']}.crate"]["sha256"], owner=owner
        )
        for p in metadata
    }
    result = {}
    for item in metadata:
        filename = f"{item['name']}-{item['vers']}.crate"
        digest = manifest["assets"][filename]["sha256"]
        if statuses[item["name"]] != "verified_existing":
            meta = json.dumps(item, separators=(",", ":")).encode()
            data = (directory / filename).read_bytes()
            body = struct.pack("<I", len(meta)) + meta + struct.pack("<I", len(data)) + data
            raw, unused = request(
                "https://crates.io/api/v1/crates/new",
                method="PUT",
                data=body,
                headers={"Authorization": token, "Content-Type": "application/octet-stream"},
            )
            if json.loads(raw).get("errors"):
                raise ReleaseError(
                    "crates.io rejected publication; inspect account verification, create/publish scope and ownership"
                )
        wait_for(lambda: crate_index(item, digest))
        result[item["name"]] = {"version": item["vers"], "sha256": digest, "verified": True}
        state(directory, "crates", result)
    return result


def pypi_status(directory, manifest):
    v = version()
    names = [f"leakscope-{v.python}-py3-none-any.whl", f"leakscope-{v.python}.tar.gz"]
    project = get("https://pypi.org/pypi/leakscope/json", missing=True)
    if project:
        urls = project["info"].get("project_urls") or {}
        if "https://github.com/" + REPOSITORY not in {str(x).rstrip("/") for x in urls.values()}:
            raise ReleaseError(
                "PyPI project-name collision: leakscope belongs to another source repository"
            )
    release = get("https://pypi.org/pypi/leakscope/" + v.python + "/json", missing=True)
    existing = {}
    if release:
        assert release["info"]["name"] == "leakscope" and release["info"]["version"] == v.python
        for item in release["urls"]:
            name = item["filename"]
            if (
                name not in names
                or item["digests"]["sha256"] != manifest["assets"][name]["sha256"]
                or item.get("yanked")
            ):
                raise ReleaseError(
                    "Immutable PyPI file conflicts with the intended release; manual reconciliation required"
                )
            existing[name] = item["digests"]["sha256"]
    return names, existing


def publish_pypi(directory, manifest):
    authorized("pypi")
    names, existing = pypi_status(directory, manifest)
    missing = [str(directory / n) for n in names if n not in existing]
    if missing:
        env = {
            **os.environ,
            "TWINE_REPOSITORY_URL": "https://upload.pypi.org/legacy/",
            "TWINE_NON_INTERACTIVE": "1",
            "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "twine",
                "upload",
                "--non-interactive",
                "--disable-progress-bar",
                *missing,
            ],
            env=env,
        )
        if result.returncode:
            raise ReleaseError(
                "PyPI upload failed; check project name, account verification and existing PYPI_TOKEN scope. Rerun inspects each file; no skip-existing is used."
            )
    result = wait_for(
        lambda: (
            files if len(files := pypi_status(directory, manifest)[1]) == len(names) else False
        )
    )
    state(directory, "pypi", result)
    return result


def registry_plan(directory):
    from release_bundle import verify

    manifest = verify(directory)
    metadata = json.loads((directory / "cargo-publish.json").read_text())
    return {
        "crates": {
            p["name"]: crate_status(
                p, manifest["assets"][f"{p['name']}-{p['vers']}.crate"]["sha256"]
            )
            for p in metadata
        },
        "pypi_missing": sorted(
            set(pypi_status(directory, manifest)[0]) - set(pypi_status(directory, manifest)[1])
        ),
        "public_writes": False,
    }


def gh(*arguments, capture=False):
    return (
        subprocess.check_output(["gh", *arguments], text=True)
        if capture
        else subprocess.run(["gh", *arguments], check=True)
    )


def github_release():
    return get(
        f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{version().metadata()['tag']}",
        missing=True,
        headers={"Authorization": "Bearer " + os.environ.get("GH_TOKEN", "")},
    )


def recover(directory):
    from release_bundle import extract_bundle

    release = github_release()
    if release is None:
        return {"recovered": False}
    bundle_name = "leakscope-release-" + version().semver + ".tar.gz"
    if bundle_name not in {a["name"] for a in release["assets"]}:
        raise ReleaseError(
            "Existing release has no immutable recovery bundle; inspect the draft or recover the original validated Actions artifact before continuing"
        )
    with tempfile.TemporaryDirectory() as tmp:
        gh(
            "release",
            "download",
            version().metadata()["tag"],
            "--repo",
            REPOSITORY,
            "--pattern",
            bundle_name,
            "--dir",
            tmp,
            capture=True,
        )
        manifest = extract_bundle(Path(tmp) / bundle_name, directory)
    return {"recovered": True, "commit": manifest["commit"]}


def release_assets(directory):
    from release_bundle import archive_bundle

    return sorted(directory.iterdir()) + [archive_bundle(directory)]


def draft(directory, manifest):
    authorized("draft")
    release = github_release()
    tag = manifest["tag"]
    if release is None:
        gh(
            "release",
            "create",
            tag,
            "--repo",
            REPOSITORY,
            "--draft",
            "--target",
            manifest["commit"],
            "--title",
            "LeakScope " + manifest["version"],
            "--notes-file",
            str(directory / "release-notes.md"),
            *(["--prerelease"] if manifest["channel"] == "prerelease" else []),
        )
        release = github_release()
    assert release["tag_name"] == tag
    assert release["target_commitish"] == manifest["commit"], (
        "Existing GitHub Release source differs; manual reconciliation required"
    )
    assets = release_assets(directory)
    existing = {a["name"]: a for a in release["assets"]}
    allowed = {p.name for p in assets} | {"publication-state.json"}
    assert set(existing) <= allowed, "Unexpected GitHub Release assets"
    # Anchor the full validated bundle first so a partial upload can be recovered.
    for path in sorted(assets, key=lambda p: (not p.name.startswith("leakscope-release-"), p.name)):
        if path.name in existing:
            item = existing[path.name]
            if item.get("digest"):
                assert item["digest"] == "sha256:" + sha(path), "GitHub asset checksum conflict"
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    gh(
                        "release",
                        "download",
                        tag,
                        "--repo",
                        REPOSITORY,
                        "--pattern",
                        path.name,
                        "--dir",
                        tmp,
                    )
                    assert sha(Path(tmp) / path.name) == sha(path), "GitHub asset checksum conflict"
        else:
            assert release["draft"], "Finalized GitHub Release has missing assets"
            gh("release", "upload", tag, str(path), "--repo", REPOSITORY)
    return {"draft": release["draft"], "commit": manifest["commit"]}


def ghcr_manifest(tag, *, publishing=False):
    auth = base64.b64encode(
        (os.environ.get("GITHUB_ACTOR", "") + ":" + os.environ.get("GH_TOKEN", "")).encode()
    ).decode()
    token = get(
        "https://ghcr.io/token?service=ghcr.io&scope=repository:polsala/leakscope:"
        + ("pull,push" if publishing else "pull"),
        headers={"Authorization": "Basic " + auth},
    )["token"]
    raw, headers = request(
        "https://ghcr.io/v2/polsala/leakscope/manifests/" + tag,
        missing=True,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.docker.distribution.manifest.v2+json",
        },
    )
    if raw is None:
        return None
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    assert headers.get("Docker-Content-Digest", headers.get("docker-content-digest")) == digest
    return json.loads(raw), digest


def publish_ghcr(directory, manifest):
    authorized("ghcr")
    current = ghcr_manifest(manifest["version"], publishing=True)
    if current and current[0].get("config", {}).get("digest") != manifest["image_config_digest"]:
        raise ReleaseError(
            "Immutable versioned GHCR tag points to a different image; refusing overwrite"
        )
    with tempfile.TemporaryDirectory(prefix="leakscope-docker-auth-") as tmp:
        env = {**os.environ, "DOCKER_CONFIG": tmp}
        if current is None:
            subprocess.run(
                [
                    "docker",
                    "login",
                    "ghcr.io",
                    "--username",
                    os.environ["GITHUB_ACTOR"],
                    "--password-stdin",
                ],
                input=os.environ["GH_TOKEN"].encode(),
                env=env,
                check=True,
            )
            subprocess.run(
                ["docker", "load", "--input", str(directory / "image.tar")], env=env, check=True
            )
            subprocess.run(["docker", "push", manifest["image"]], env=env, check=True)
        current = wait_for(lambda: ghcr_manifest(manifest["version"], publishing=True))
        assert current[0]["config"]["digest"] == manifest["image_config_digest"]
    result = {
        "reference": manifest["image"],
        "digest": current[1],
        "config_digest": manifest["image_config_digest"],
    }
    state(directory, "ghcr", result)
    return result


def state(directory, component, result):
    # Outside immutable bundle; never write credentials or mutable files into it.
    path = directory.parent / ("publication-" + component + ".json")
    path.write_text(
        json.dumps(
            {
                "commit": json.loads((directory / "release-manifest.json").read_text())["commit"],
                "version": version().semver,
                "component": component,
                "result": result,
            },
            indent=2,
        )
        + "\n"
    )


def finalize(directory, manifest):
    authorized("finalize")
    metadata = json.loads((directory / "cargo-publish.json").read_text())
    for item in metadata:
        digest = manifest["assets"][f"{item['name']}-{item['vers']}.crate"]["sha256"]
        assert crate_status(item, digest) == "verified_existing"
        assert crate_index(item, digest)
    names, files = pypi_status(directory, manifest)
    assert set(names) == set(files), "PyPI publication is incomplete"
    image = ghcr_manifest(manifest["version"])
    assert image and image[0]["config"]["digest"] == manifest["image_config_digest"]
    draft(directory, manifest)
    if manifest["channel"] == "stable":
        # Verified again immediately before promotion; no stable/latest bypass.
        from release_request import stable_gate

        stable_gate(directory / "release-evidence.json")
        latest = get(
            f"https://api.github.com/repos/{REPOSITORY}/releases/latest",
            missing=True,
            headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"]},
        )
        if latest:
            old = tuple(int(x) for x in latest["tag_name"].removeprefix("v").split("."))
            new = tuple(int(x) for x in manifest["version"].split("."))
            if old > new:
                raise ReleaseError(
                    "Refusing to replace a newer stable latest release; reconcile the older draft explicitly"
                )
        with tempfile.TemporaryDirectory(prefix="leakscope-docker-auth-") as tmp:
            env = {**os.environ, "DOCKER_CONFIG": tmp}
            subprocess.run(
                [
                    "docker",
                    "login",
                    "ghcr.io",
                    "--username",
                    os.environ["GITHUB_ACTOR"],
                    "--password-stdin",
                ],
                input=os.environ["GH_TOKEN"].encode(),
                env=env,
                check=True,
            )
            subprocess.run(["docker", "pull", IMAGE + "@" + image[1]], env=env, check=True)
            subprocess.run(
                ["docker", "tag", IMAGE + "@" + image[1], IMAGE + ":latest"], env=env, check=True
            )
            subprocess.run(["docker", "push", IMAGE + ":latest"], env=env, check=True)
            assert ghcr_manifest("latest")[1] == image[1], "latest digest verification failed"
    result = {
        "commit": manifest["commit"],
        "version": manifest["version"],
        "github_release": "complete",
        "crates": [p["name"] for p in metadata],
        "pypi": files,
        "ghcr_digest": image[1],
        "production_ready": manifest["channel"] == "stable",
    }
    path = directory.parent / "publication-state.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    release = github_release()
    if "publication-state.json" not in {a["name"] for a in release["assets"]}:
        gh("release", "upload", manifest["tag"], str(path), "--repo", REPOSITORY)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            gh(
                "release",
                "download",
                manifest["tag"],
                "--repo",
                REPOSITORY,
                "--pattern",
                "publication-state.json",
                "--dir",
                tmp,
                capture=True,
            )
            assert sha(Path(tmp) / "publication-state.json") == sha(path), (
                "Existing final publication state conflicts"
            )
    gh(
        "release",
        "edit",
        manifest["tag"],
        "--repo",
        REPOSITORY,
        "--draft=false",
        "--prerelease=" + str(manifest["channel"] == "prerelease").lower(),
        "--latest=" + str(manifest["channel"] == "stable").lower(),
    )
    state(directory, "finalize", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "component", choices=["crates", "pypi", "ghcr", "draft", "finalize", "plan"]
    )
    parser.add_argument("--directory", type=Path, default=ROOT / "artifacts/release")
    args = parser.parse_args()
    if args.component == "plan":
        result = registry_plan(args.directory)
    else:
        authorized(args.component)
        from release_bundle import verify

        manifest = verify(args.directory)
        from release_request import publication_gate

        publication_gate(manifest, args.directory)
        fn = {
            "crates": publish_crates,
            "pypi": publish_pypi,
            "ghcr": publish_ghcr,
            "draft": draft,
            "finalize": finalize,
        }[args.component]
        result = fn(args.directory, manifest)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
