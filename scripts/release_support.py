"""Shared release contracts. No registry writes or credentials are needed here."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "polsala/LeakScope"
IMAGE = "ghcr.io/polsala/leakscope"


@dataclass(frozen=True)
class Version:
    semver: str

    def __post_init__(self):
        if not re.fullmatch(
            r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(alpha|beta|rc)\.([1-9]\d*))?",
            self.semver,
        ):
            raise ValueError(
                "Use MAJOR.MINOR.PATCH[-alpha.N|-beta.N|-rc.N], without v or leading zeros"
            )

    @property
    def python(self):
        return self.semver.replace("-alpha.", "a").replace("-beta.", "b").replace("-rc.", "rc")

    @property
    def debian(self):
        return (
            self.semver.replace("-alpha.", "~alpha")
            .replace("-beta.", "~beta")
            .replace("-rc.", "~rc")
        )

    @property
    def channel(self):
        return "prerelease" if "-" in self.semver else "stable"

    def metadata(self):
        return {
            "version": self.semver,
            "python": self.python,
            "debian": self.debian,
            "tag": "v" + self.semver,
            "channel": self.channel,
            "image": IMAGE + ":" + self.semver,
            "stage": "leakscope-" + self.semver + "-linux-x86_64",
        }


def version(root=ROOT):
    return Version(json.loads((root / "release-version.json").read_text())["version"])


def run(command, *, root=ROOT, **kwargs):
    # Registry secrets never reach builds, tests, package hooks or lock updates.
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "PYPI_TOKEN",
            "CRATES_IO_TOKEN",
            "CARGO_REGISTRY_TOKEN",
            "TWINE_PASSWORD",
            "RELEASE_GPG_KEY",
        }
    }
    env.setdefault("UV_CACHE_DIR", str(root / ".cache/uv"))
    return subprocess.run(command, cwd=root, env=env, check=True, **kwargs)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def crates(root=ROOT):
    workspace = tomllib.loads((root / "Cargo.toml").read_text())
    result = {}
    for member in workspace["workspace"]["members"]:
        doc = tomllib.loads((root / member / "Cargo.toml").read_text())
        package = doc["package"]
        if package.get("publish") is False:
            continue
        deps = []
        for kind in ["dependencies", "build-dependencies", "dev-dependencies"]:
            for alias, dep in doc.get(kind, {}).items():
                if isinstance(dep, dict) and "path" in dep:
                    deps.append(dep.get("package", alias))
        result[package["name"]] = {"path": member, "dependencies": sorted(set(deps))}
    return result


def publication_order(root=ROOT):
    graph = crates(root)
    order = []
    while len(order) != len(graph):
        ready = sorted(
            n for n, p in graph.items() if n not in order and set(p["dependencies"]) <= set(order)
        )
        if not ready:
            raise ValueError(
                "Cargo publication graph has a cycle or depends on an unpublished internal crate"
            )
        order.extend(ready)
    return order


def check(root=ROOT, tag=None):
    v = version(root)
    cargo = tomllib.loads((root / "Cargo.toml").read_text())
    assert cargo["workspace"]["package"]["version"] == v.semver, "Workspace version mismatch"
    assert tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"] == v.python, (
        "Python version mismatch"
    )
    for path in ["package.json", "apps/web/package.json"]:
        assert json.loads((root / path).read_text())["version"] == v.semver, path
    assert re.search(
        r'__version__ = "' + re.escape(v.python) + r'"',
        (root / "apps/api/leakscope_api/__init__.py").read_text(),
    ), "Runtime version mismatch"
    assert (root / "legacy/py27-agent/VERSION").read_text().strip() == v.python, (
        "Agent version mismatch"
    )
    lock = tomllib.loads((root / "Cargo.lock").read_text())
    locked = {
        p["name"]: p["version"] for p in lock["package"] if p["name"].startswith("leakscope-")
    }
    uv = tomllib.loads((root / "uv.lock").read_text())
    assert next(p["version"] for p in uv["package"] if p["name"] == "leakscope") == v.python, (
        "uv.lock mismatch"
    )
    for name, item in crates(root).items():
        p = tomllib.loads((root / item["path"] / "Cargo.toml").read_text())
        assert p["package"]["version"] == {"workspace": True}, name
        assert locked[name] == v.semver, name + " lock mismatch"
        for dep in p.get("dependencies", {}).values():
            if isinstance(dep, dict) and "path" in dep:
                assert dep["version"] == "=" + v.semver, name + " dependency version mismatch"
        for key in ["description", "readme", "keywords"]:
            assert p["package"].get(key), name + " missing " + key
        assert (root / item["path"] / "README.md").is_file()
    publication_order(root)
    if tag is not None:
        assert tag == "v" + v.semver, "Tag and release manifests do not match"
    return v


def prepare(value, root=ROOT, runner=run):
    v = Version(value)
    (root / "release-version.json").write_text(json.dumps({"version": v.semver}) + "\n")
    for path in ["package.json", "apps/web/package.json"]:
        p = root / path
        doc = json.loads(p.read_text())
        doc["version"] = v.semver
        p.write_text(json.dumps(doc, indent=2) + "\n")
    for filename, value in [("Cargo.toml", v.semver), ("pyproject.toml", v.python)]:
        p = root / filename
        p.write_text(
            re.sub(
                r'^version = "[^"]+"',
                'version = "' + value + '"',
                p.read_text(),
                count=1,
                flags=re.M,
            )
        )
    p = root / "apps/api/leakscope_api/__init__.py"
    p.write_text(
        re.sub(r'__version__ = "[^"]+"', '__version__ = "' + v.python + '"', p.read_text())
    )
    (root / "legacy/py27-agent/VERSION").write_text(v.python + "\n")
    for item in crates(root).values():
        p = root / item["path"] / "Cargo.toml"
        p.write_text(
            re.sub(r'(path = "[^"]+", version = ")[^"]+', r"\g<1>=" + v.semver, p.read_text())
        )
    runner(["cargo", "update", "--workspace", "--offline"], root=root)
    runner([str(root / ".venv/bin/uv"), "lock", "--offline"], root=root)
    runner(["corepack", "pnpm", "install", "--lockfile-only", "--offline"], root=root)
    changelog = root / "CHANGELOG.md"
    text = changelog.read_text()
    marker = "## " + v.semver
    if marker not in text:
        title, _, body = text.partition("\n")
        changelog.write_text(
            title
            + "\n\n"
            + marker
            + "\n\nPrepared for review; release notes are generated from reviewed commits.\n"
            + body
        )
    return check(root)
