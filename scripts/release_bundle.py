"""Immutable local release bundles, real installation tests and safe recovery."""

import email
import gzip
import json
from leakscope_api.readiness import fingerprint
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from release_support import ROOT, check, publication_order, run, sha, version


def git_sha():
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def expected_assets(v):
    return [
        v.metadata()["stage"] + ".tar.gz",
        f"leakscope_{v.debian}_amd64.deb",
        f"leakscope-{v.python}-py3-none-any.whl",
        f"leakscope-{v.python}.tar.gz",
        f"leakscope-source-{v.semver}.tar.gz",
        "sbom.cdx.json",
        "release-readiness.json",
        "release-evidence.json",
        "compatibility.json",
        "release-notes.md",
        "image.tar",
        "cargo-publish.json",
        "requirements-publish.txt",
    ] + [f"{n}-{v.semver}.crate" for n in publication_order()]


def verify(directory):
    directory = Path(directory)
    assert (directory / "release-manifest.json").stat().st_size < 2 * 1024**2
    manifest = json.loads((directory / "release-manifest.json").read_text())
    v = check(tag=manifest["tag"])
    assert manifest["commit"] == git_sha(), "Bundle source commit mismatch"
    assert manifest["version"] == v.semver and manifest["python"] == v.python
    assert manifest["channel"] == v.channel
    assert set(manifest["assets"]) == set(expected_assets(v)), "Unexpected release asset set"
    expected = set(manifest["assets"]) | {"SHA256SUMS", "release-manifest.json"}
    assert all(p.is_file() and not p.is_symlink() for p in directory.iterdir()), (
        "Unsafe bundle entry"
    )
    assert {p.name for p in directory.iterdir()} == expected, (
        "Missing or stale files in release bundle"
    )
    for name, item in manifest["assets"].items():
        assert Path(name).name == name and not (directory / name).is_symlink(), "Unsafe asset path"
        assert (directory / name).stat().st_size == item["size"]
        assert sha(directory / name) == item["sha256"], "Asset checksum mismatch: " + name
    checks = "".join(
        f"{sha(directory / n)}  {n}\n"
        for n in sorted(set(manifest["assets"]) | {"release-manifest.json"})
    )
    assert (directory / "SHA256SUMS").read_text() == checks, "Checksum manifest mismatch"
    assert all(
        manifest["validation"].get(k) is True
        for k in ["cargo", "wheel", "installed_ubuntu", "oci_runtime"]
    ), "Incomplete build validation"
    assert manifest["source_fingerprint"] == fingerprint(ROOT), "Bundle input fingerprint mismatch"
    return manifest


def wheel_check(directory):
    v = version()
    wheel = directory / f"leakscope-{v.python}-py3-none-any.whl"
    source = directory / f"leakscope-{v.python}.tar.gz"
    run(
        [
            str(ROOT / ".venv/bin/python"),
            "-m",
            "twine",
            "check",
            "--strict",
            str(wheel),
            str(source),
        ]
    )
    with zipfile.ZipFile(wheel) as package:
        metadata = email.message_from_bytes(
            package.read(f"leakscope-{v.python}.dist-info/METADATA")
        )
        assert metadata["Name"] == "leakscope" and metadata["Version"] == v.python
        assert metadata["Requires-Python"] == ">=3.11"
        assert (
            "does **not** bundle"
            in package.read(f"leakscope-{v.python}.dist-info/METADATA").decode()
        )
        assert any("migrations/versions/" in n for n in package.namelist())
    with tempfile.TemporaryDirectory(prefix="leakscope-wheel-") as temporary:
        prefix = Path(temporary) / "venv"
        run([sys.executable, "-m", "venv", str(prefix)])
        wheels = ROOT / "artifacts" / v.metadata()["stage"] / "wheels"
        run(
            [
                str(prefix / "bin/python"),
                "-I",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                str(wheels),
                str(wheel),
            ]
        )
        run([str(prefix / "bin/leakscope"), "--version"], root=Path(temporary))
        code = (
            "import leakscope_api,importlib.metadata as m; from pathlib import Path; from leakscope_api.db import database; assert leakscope_api.__version__ == m.version('leakscope') == "
            + repr(v.python)
            + "; e,_=database(Path('installed.sqlite3')); e.dispose(); import leakscope_api.app; print('Installed imports, CLI metadata and all migrations verified')"
        )
        run([str(prefix / "bin/python"), "-I", "-c", code], root=Path(temporary))


def image_check(tag, metadata):
    run(
        [
            "docker",
            "build",
            "--platform",
            "linux/amd64",
            "--provenance=false",
            "-f",
            "packaging/docker/Dockerfile",
            "--build-arg",
            "DISTRIBUTION=artifacts/" + metadata["stage"],
            "--build-arg",
            "RELEASE_VERSION=" + metadata["version"],
            "--build-arg",
            "SOURCE_COMMIT=" + git_sha(),
            "--build-arg",
            "BUILD_CREATED="
            + subprocess.check_output(
                ["git", "show", "-s", "--format=%cI", "HEAD"], text=True
            ).strip(),
            "-t",
            tag,
            ".",
        ]
    )
    info = json.loads(subprocess.check_output(["docker", "image", "inspect", tag]))[0]
    assert info["Config"]["User"] == "10001:10001"
    assert info["Config"]["Labels"]["org.opencontainers.image.revision"] == git_sha()
    # Actual installed application journey, no source imports, networking or BPF capabilities.
    run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "-v",
            str(ROOT / "scripts") + ":/qa/scripts:ro",
            "-v",
            str(ROOT / "tests/support") + ":/qa/tests/support:ro",
            "--entrypoint",
            "/opt/leakscope/venv/bin/python",
            tag,
            "-I",
            "/qa/scripts/validate-package.py",
            "--prefix",
            "/opt/leakscope",
        ]
    )
    return info["Id"]


def create_manifest(directory, image_id):
    v = version()
    assets = expected_assets(v)
    manifest = {
        **v.metadata(),
        "commit": git_sha(),
        "image_config_digest": image_id,
        "production_certified": json.loads((directory / "release-readiness.json").read_text())[
            "production_ready"
        ],
        "source_fingerprint": __import__(
            "leakscope_api.readiness", fromlist=["fingerprint"]
        ).fingerprint(ROOT),
        "validation": {"cargo": True, "wheel": True, "installed_ubuntu": True, "oci_runtime": True},
        "assets": {
            name: {"sha256": sha(directory / name), "size": (directory / name).stat().st_size}
            for name in assets
        },
    }
    (directory / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    (directory / "SHA256SUMS").write_text(
        "".join(f"{sha(directory / n)}  {n}\n" for n in sorted(assets + ["release-manifest.json"]))
    )
    return verify(directory)


def build(directory):
    v = check()
    build_commit, build_fingerprint = git_sha(), fingerprint(ROOT)
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT), (
        "Commit reviewed source changes before building a release"
    )
    if directory.exists():
        raise ValueError(
            "Release output already exists; use verify/recover, or choose a new empty --directory"
        )
    directory.mkdir(parents=True)
    run(["bash", "packaging/release/package.sh"])
    run(["cargo", "package", "--workspace", "--locked"])
    run(["cargo", "publish", "--workspace", "--locked", "--dry-run"])
    run(["bash", "scripts/test-installed-ubuntu.sh"])
    run(
        [
            str(ROOT / ".venv/bin/uv"),
            "export",
            "--frozen",
            "--only-group",
            "release",
            "--no-emit-project",
            "-o",
            str(directory / "requirements-publish.txt"),
        ]
    )
    from release_publish import cargo_metadata

    publish = []
    target = json.loads(
        subprocess.check_output(["cargo", "metadata", "--no-deps", "--format-version", "1"])
    )["target_directory"]
    for name in publication_order():
        path = Path(target) / "package" / f"{name}-{v.semver}.crate"
        shutil.copyfile(path, directory / path.name)
        publish.append(cargo_metadata(path, git_sha()))
    (directory / "cargo-publish.json").write_text(json.dumps(publish, indent=2) + "\n")
    for name in [
        v.metadata()["stage"] + ".tar.gz",
        f"leakscope_{v.debian}_amd64.deb",
        f"leakscope-{v.python}-py3-none-any.whl",
        f"leakscope-{v.python}.tar.gz",
        f"leakscope-source-{v.semver}.tar.gz",
        "sbom.cdx.json",
    ]:
        shutil.copyfile(ROOT / "artifacts" / name, directory / name)
    assert (
        subprocess.check_output(
            ["dpkg-deb", "-f", str(directory / f"leakscope_{v.debian}_amd64.deb"), "Version"],
            text=True,
        ).strip()
        == v.debian
    ), "Debian package metadata mismatch"
    wheel_check(directory)
    image_id = image_check(v.metadata()["image"], v.metadata())
    run(["docker", "save", "--output", str(directory / "image.tar"), v.metadata()["image"]])
    from leakscope_api.readiness import evaluate

    receipts = ROOT / "artifacts/release-evidence.json"
    (directory / "release-evidence.json").write_text(
        receipts.read_text() if receipts.exists() else '{"gates": {}}\n'
    )
    report = evaluate(directory / "release-evidence.json", expected_fingerprint=fingerprint(ROOT))
    (directory / "release-readiness.json").write_text(json.dumps(report, indent=2) + "\n")
    compatibility = {
        p.stem: p.read_text()
        for p in sorted((ROOT / "artifacts/compatibility").glob("ubuntu-*.txt"))
    }
    (directory / "compatibility.json").write_text(
        json.dumps(
            {
                "userlands": compatibility,
                "kernel_validation": "Not established by container compatibility tests; see release readiness",
                "commit": git_sha(),
            },
            indent=2,
        )
        + "\n"
    )
    history = subprocess.check_output(
        ["git", "log", "--max-count=50", "--format=- %s (%h)", "HEAD"], text=True
    )
    (directory / "release-notes.md").write_text(
        f"# LeakScope {v.semver}\n\n"
        + (
            "Engineering prerelease. Production certification is incomplete.\n"
            if v.channel == "prerelease"
            else "Stable publication requires independent current-source production certification.\n"
        )
        + "\nPython component: native binaries/web assets are distributed separately in the standalone package.\nNative tracing remains opt-in; image runs unprivileged with no BPF capabilities.\n\nSource: `"
        + git_sha()
        + "`.\nSee release-readiness.json and compatibility.json for precise qualification limits.\n\n## Recent reviewed commits\n\n"
        + history
    )
    assert git_sha() == build_commit and fingerprint(ROOT) == build_fingerprint, (
        "Sources changed during the build"
    )
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT), (
        "Worktree changed during the build"
    )
    return create_manifest(directory, image_id)


def archive_bundle(directory):
    verify(directory)
    output = directory.parent / ("leakscope-release-" + version().semver + ".tar.gz")
    epoch = int(subprocess.check_output(["git", "show", "-s", "--format=%ct", "HEAD"], text=True))
    with (
        output.open("wb") as stream,
        gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=epoch) as compressed,
        tarfile.open(fileobj=compressed, mode="w|") as archive,
    ):
        for path in sorted(directory.iterdir()):
            info = archive.gettarinfo(str(path), arcname=path.name)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = epoch
            info.mode = 0o644
            with path.open("rb") as source:
                archive.addfile(info, source)
    return output


def extract_bundle(path, directory):
    # No extraction before name/type/size validation. Packages/images are opaque assets.
    with tarfile.open(path, "r:gz") as archive:
        members = []
        for member in archive:
            members.append(member)
            assert len(members) <= len(expected_assets(version())) + 2, "Too many bundle members"
        allowed = set(expected_assets(version())) | {"SHA256SUMS", "release-manifest.json"}
        assert len(members) == len(allowed) and {m.name for m in members} == allowed
        assert all(
            m.isfile() and m.name == Path(m.name).name and 0 <= m.size <= 2 * 1024**3
            for m in members
        )
        assert sum(m.size for m in members) < 3 * 1024**3
        directory.mkdir(parents=True, exist_ok=False)
        archive.extractall(directory, filter="data")
    return verify(directory)


def execute(command, directory):
    if command == "recover":
        from release_publish import recover

        return recover(directory)
    if command == "verify":
        return verify(directory)
    if command in {"build", "dry-run"}:
        manifest = build(directory) if not directory.exists() else verify(directory)
        archive_bundle(directory)
        if command == "dry-run":
            from release_publish import registry_plan

            return {
                "published": False,
                "manifest": manifest,
                "registry_plan": registry_plan(directory),
            }
        return manifest
    raise ValueError(command)
