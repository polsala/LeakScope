"""Refresh only our audited wrapper suffix in a previously patched source tree."""

from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
path = Path(sys.argv[1])
source = path.read_text()
marker = "/* LeakScope laboratory wrappers. Recursion is suppressed per native thread. */"
if marker not in source:
    raise SystemExit("Expected exact LeakScope wrapper marker is missing")
patch = (root / "legacy/cpython-2.7-patch/cpython-2.7.18.patch").read_text()
body = (
    "\n".join(
        line[1:] for line in patch[patch.index("+" + marker) :].splitlines() if line.startswith("+")
    )
    + "\n"
)
path.write_text(source[: source.index(marker)] + body)
