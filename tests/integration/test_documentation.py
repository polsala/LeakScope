"""Offline documentation correctness, including real CLI parsing without execution."""

import importlib.util
from pathlib import Path
import re

import yaml

from leakscope_api.config import Config

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts/check_docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_documentation_links_and_cli_examples():
    files = docs.tracked_files(ROOT)
    assert docs.check(ROOT, files) == []
    errors, count = docs.check_cli(files)
    assert errors == []
    assert count >= 25  # Real examples across installation, guides and reference.


def test_documented_configuration_uses_real_fields():
    for page in (ROOT / "docs").rglob("*.md"):
        for block in re.findall(r"^```yaml\s*\n(.*?)^```", page.read_text(), re.M | re.S):
            Config.model_validate(yaml.safe_load(block))
    Config.model_validate(yaml.safe_load((ROOT / "packaging/config.example.yaml").read_text()))


def test_links_anchors_fences_and_navigation(tmp_path):
    index = write(tmp_path, "docs/README.md", "# Docs\n\n[Guide](guide.md#source-location)\n")
    guide = write(
        tmp_path,
        "docs/" + "guide.md",
        '# Guide\n\n## Source location\n\n```python\n# fake heading\n"[fake](missing.md)"\n```\n',
    )
    assert docs.check(tmp_path, [index, guide]) == []
    guide.write_text(guide.read_text() + "\n[broken](missing.md)\n[anchor](#absent)\n")
    errors = docs.check(tmp_path, [index, guide])
    assert any("missing local target" in e for e in errors)
    assert any("missing anchor" in e for e in errors)
    orphan = write(tmp_path, "docs/" + "orphan.md", "# Orphan\n")
    assert any("not reachable" in e for e in docs.check(tmp_path, [index, guide, orphan]))


def test_reference_links_escaped_paths_and_duplicates(tmp_path):
    index = write(
        tmp_path,
        "docs/README.md",
        "# Docs\n\n[guide][target]\n\n[target]: <space%20guide.md#repeated-1>\n",
    )
    guide = write(tmp_path, "docs/space guide.md", "# Guide\n\n## Repeated\n\n## Repeated\n")
    assert docs.check(tmp_path, [index, guide]) == []
    assert docs.anchors(guide.read_text()) == {"guide", "repeated", "repeated-1"}
    index.write_text(index.read_text() + "\n[x][undefined]\n")
    assert any("undefined link reference" in e for e in docs.check(tmp_path, [index, guide]))


def test_stale_paths_positioning_and_heading_checks(tmp_path):
    index = write(tmp_path, "docs/README.md", "# Docs\n\n### Jump\n\nMemray 0.1.0\n")
    source = write(tmp_path, "example.sh", "# docs/" + "deleted.md\n")
    errors = docs.check(tmp_path, [index, source])
    for reason in [
        "skipped heading level",
        "competing-profiler",
        "stale initial release",
        "stale documentation path",
    ]:
        assert any(reason in e for e in errors), errors


def test_cli_smoke_rejects_invalid_flags_and_durations(tmp_path):
    page = write(
        tmp_path,
        "example.md",
        "# Example\n\n```sh\nleakscope monitor --pid 1234 \\\n  --duration 30m --json\nleakscope capture --pid 1234 --duration 30m\nleakscope ps --invented-flag\n```\n",
    )
    errors, count = docs.check_cli([page])
    assert count == 3
    assert len(errors) == 2
