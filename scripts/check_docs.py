#!/usr/bin/env python3
"""Check repository Markdown offline; optionally format and parse CLI examples."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path
import re
import shlex
import subprocess
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
# Deliberately limited to the repository's inline/reference-link Markdown style.
LINK = re.compile(r"\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+[\"'][^)]*[\"'])?\)")
DEFINITION = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", re.M)
REFERENCE = re.compile(r"\[([^\]\n]+)\]\[([^\]\n]*)\]")
DOC_PATH = re.compile(r"(?<![\w/])docs/(?:[\w.-]+/)*[\w.-]+\.md\b")
COMPETITORS = re.compile(r"\b(memray|scalene|filprofiler|heaptrack)\b", re.I)


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return sorted({root / p.decode() for p in result.stdout.split(b"\0") if p})


def without_fences(text: str) -> str:
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker and fence is None:
            fence = marker.group(1)
            lines.append("")
        elif fence and re.fullmatch(
            r"\s*" + re.escape(fence[0]) + r"{" + str(len(fence)) + r",}\s*", line
        ):
            fence = None
            lines.append("")
        else:
            lines.append("" if fence else line)
    return "\n".join(lines)


def anchors(text: str) -> set[str]:
    found: set[str] = set()
    for title in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", without_fences(text), re.M):
        title = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", title)
        title = re.sub(r"<[^>]*>", "", title).lower()
        slug = re.sub(r"[^\w\- ]", "", title).replace(" ", "-")
        candidate, index = slug, 0
        while candidate in found:
            index += 1
            candidate = f"{slug}-{index}"
        found.add(candidate)
    found.update(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)', text))
    return found


def local_target(root: Path, source: Path, target: str) -> tuple[Path, str] | None:
    value = urlsplit(target.strip("<>"))
    if value.scheme or value.netloc:
        return None
    if value.path.startswith("/"):
        path = root / unquote(value.path).lstrip("/")
    else:
        path = source.parent / unquote(value.path) if value.path else source
    return path.resolve(), unquote(value.fragment)


def check(root: Path, files: list[Path]) -> list[str]:
    root = root.resolve()
    markdown = [p for p in files if p.is_file() and p.suffix == ".md"]
    errors = []
    edges: dict[Path, set[Path]] = {}
    for path in markdown:
        label = str(path.relative_to(root))
        text = path.read_text()
        plain = without_fences(text)
        headings = re.findall(r"^(#{1,6})\s+(.+)$", plain, re.M)
        if sum(len(level) == 1 for level, _ in headings) != 1:
            errors.append(f"{label}: require exactly one level-one heading")
        previous = 0
        for level, title in headings:
            if len(level) > previous + 1:
                errors.append(f"{label}: skipped heading level: {title}")
            previous = len(level)
        if not text.endswith("\n") or text.endswith("\n\n"):
            errors.append(f"{label}: require one final newline")
        if any(line.rstrip() != line for line in text.splitlines()):
            errors.append(f"{label}: trailing whitespace")
        if not label.startswith("docs/evidence/") and (
            path.name in {"README.md", "PYPI.md"} or label.startswith("docs/")
        ):
            if COMPETITORS.search(plain):
                errors.append(f"{label}: competing-profiler product reference")
            if re.search(r"(?<![\d.])v?0\.1\.0(?![\d.])", plain):
                errors.append(f"{label}: stale initial release version")
        definitions = {k.casefold(): v for k, v in DEFINITION.findall(plain)}
        links = LINK.findall(plain) + list(definitions.values())
        for title, reference in REFERENCE.findall(plain):
            key = (reference or title).casefold()
            if key not in definitions:
                errors.append(f"{label}: undefined link reference [{key}]")
        edges[path.resolve()] = set()
        for target in links:
            resolved = local_target(root, path, target)
            if resolved is None:
                continue
            dest, fragment = resolved
            if not dest.is_relative_to(root) or not dest.exists():
                errors.append(f"{label}: missing local target: {target}")
                continue
            if dest.suffix == ".md":
                edges[path.resolve()].add(dest)
                if fragment and fragment not in anchors(dest.read_text()):
                    errors.append(f"{label}: missing anchor: {target}")
    # Catch plain old documentation paths in scripts, workflows and comments too.
    for path in files:
        if not path.is_file() or "docs/evidence/" in str(path.relative_to(root)):
            continue
        if path.suffix not in {
            ".md",
            ".py",
            ".rs",
            ".sh",
            ".yml",
            ".yaml",
            ".toml",
            ".json",
        } and path.name not in {"Makefile", "justfile"}:
            continue
        try:
            text = path.read_text()
        except UnicodeError:
            continue
        for target in set(DOC_PATH.findall(text)):
            if not (root / target).is_file():
                errors.append(f"{path.relative_to(root)}: stale documentation path: {target}")
    index = (root / "docs/README.md").resolve()
    reached, pending = set(), [index]
    while pending:
        node = pending.pop()
        if node not in reached:
            reached.add(node)
            pending.extend(edges.get(node, set()) - reached)
    for path in markdown:
        if path.is_relative_to(root / "docs") and path.resolve() not in reached:
            errors.append(f"{path.relative_to(root)}: not reachable from docs/README.md")
    return errors


def cli_examples(path: Path) -> list[list[str]]:
    """Extract direct CLI invocations from shell fences, including continuations."""
    examples = []
    for block in re.findall(r"^```(?:sh|bash|shell)\s*\n(.*?)^```", path.read_text(), re.M | re.S):
        block = block.replace("\\\n", " ")
        for line in block.splitlines():
            words = shlex.split(line, comments=True)
            if words and words[0] in {"leakscope", ".venv/bin/leakscope"}:
                examples.append(words[1:])
    return examples


def check_cli(files: list[Path]) -> tuple[list[str], int]:
    from leakscope_api import cli

    class Parsed(Exception):
        pass

    parse = argparse.ArgumentParser.parse_args
    errors, count = [], 0
    for path in files:
        if not path.is_file() or path.suffix != ".md":
            continue
        for args in cli_examples(path):
            count += 1

            def stop_after_parsing(parser, *a, **kw):
                # Validate every flag/type/required argument without executing a command.
                parse(parser, *a, **kw)
                raise Parsed()

            output = io.StringIO()
            with (
                patch.object(argparse.ArgumentParser, "parse_args", stop_after_parsing),
                patch("sys.argv", ["leakscope", *args]),
                redirect_stdout(output),
            ):
                try:
                    cli.main()
                except Parsed:
                    pass
                except SystemExit as exc:
                    if exc.code != 0:
                        errors.append(f"{path}: invalid CLI example: {shlex.join(args)}")
    return errors, count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", action="store_true", help="Use the existing pinned Prettier")
    parser.add_argument("--write", action="store_true", help="Format files instead of checking")
    parser.add_argument(
        "--cli", action="store_true", help="Validate shell examples against the real parser"
    )
    args = parser.parse_args()
    files = [p for p in tracked_files(ROOT) if p.is_file()]
    markdown = [p for p in files if p.suffix == ".md"]
    if args.format:
        result = subprocess.run(
            [
                "corepack",
                "pnpm",
                "--dir",
                "apps/web",
                "exec",
                "prettier",
                "--write" if args.write else "--check",
                "--prose-wrap",
                "always",
                *map(str, markdown),
            ],
            cwd=ROOT,
        )
        if result.returncode:
            return result.returncode
    errors = check(ROOT, files)
    count = 0
    if args.cli:
        cli_errors, count = check_cli(markdown)
        errors.extend(cli_errors)
    for error in errors:
        print(error)
    print(
        f"Documentation: {len(markdown)} Markdown files, {count} CLI examples, {len(errors)} errors"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
