"""Release version contracts do not contact or publish to any registry."""

import json
from pathlib import Path
import shutil
import sys
import tomllib
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from release_support import ROOT, Version, check, prepare, publication_order  # noqa: E402


@pytest.mark.parametrize(
    "value,python,debian",
    [
        ("1.2.3", "1.2.3", "1.2.3"),
        ("0.2.0-rc.1", "0.2.0rc1", "0.2.0~rc1"),
        ("0.2.0-beta.12", "0.2.0b12", "0.2.0~beta12"),
        ("0.2.0-alpha.3", "0.2.0a3", "0.2.0~alpha3"),
    ],
)
def test_ecosystem_versions(value, python, debian):
    v = Version(value)
    assert v.python == python
    assert v.debian == debian
    assert v.metadata()["image"].endswith(":" + value)
    assert v.channel == ("prerelease" if "-" in value else "stable")


@pytest.mark.parametrize(
    "value", ["v1.0.0", "1.2", "01.2.3", "1.2.3-rc.0", "1.2.3-rc.01", "1.2.3+build", "1.2.3;echo x"]
)
def test_invalid_version(value):
    with pytest.raises(ValueError):
        Version(value)


def test_current_versions_and_dependency_order():
    v = check()
    assert check(tag="v" + v.semver) == v
    with pytest.raises(AssertionError, match="Tag"):
        check(tag="v99.0.0")
    order = publication_order()
    assert len(order) == 7
    assert (
        order.index("leakscope-common")
        < order.index("leakscope-procfs")
        < order.index("leakscope-sensor")
    )
    assert order.index("leakscope-capture") < order.index("leakscope-analyzer")


def test_prepare_updates_manifests_and_locks(tmp_path):
    for name in [
        "release-version.json",
        "Cargo.toml",
        "Cargo.lock",
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "apps/web/package.json",
        "apps/api/leakscope_api/__init__.py",
        "legacy/py27-agent/VERSION",
        "CHANGELOG.md",
    ]:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, p)
    shutil.copytree(ROOT / "crates", tmp_path / "crates")
    old = check()
    commands = []

    def runner(command, root):
        commands.append(command)
        if command[:2] == ["cargo", "update"]:
            p = root / "Cargo.lock"
            text = p.read_text()
            for name in publication_order(root):
                text = text.replace(
                    'name = "' + name + '"\nversion = "' + old.semver + '"',
                    'name = "' + name + '"\nversion = "0.2.0-rc.1"',
                )
            p.write_text(text)
        elif "lock" in command:
            p = root / "uv.lock"
            p.write_text(
                p.read_text().replace(
                    'name = "leakscope"\nversion = "' + old.python + '"',
                    'name = "leakscope"\nversion = "0.2.0rc1"',
                )
            )

    prepare("0.2.0-rc.1", root=tmp_path, runner=runner)
    assert check(tmp_path).python == "0.2.0rc1"
    assert commands[0] == ["cargo", "update", "--workspace", "--offline"]
    assert len(commands) == 3
    assert "## 0.2.0-rc.1" in (tmp_path / "CHANGELOG.md").read_text()
    assert json.loads((tmp_path / "apps/web/package.json").read_text())["version"] == "0.2.0-rc.1"
    assert (
        tomllib.loads((tmp_path / "crates/procfs/Cargo.toml").read_text())["dependencies"][
            "leakscope-common"
        ]["version"]
        == "=0.2.0-rc.1"
    )
