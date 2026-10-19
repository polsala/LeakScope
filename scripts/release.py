#!/usr/bin/env python3
"""Prepare, validate and build a release. This command never uploads packages."""

import argparse
import json
from pathlib import Path
from release_support import ROOT, check, prepare, publication_order, version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("version")
    p = commands.add_parser("check")
    p.add_argument("--tag")
    p = commands.add_parser("metadata")
    p.add_argument("--field")
    commands.add_parser("crates")
    for name in ["build", "dry-run", "verify", "recover"]:
        p = commands.add_parser(name)
        p.add_argument("--directory", type=Path, default=ROOT / "artifacts/release")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.version).metadata()
    elif args.command == "check":
        result = check(tag=args.tag).metadata()
    elif args.command == "metadata":
        result = version().metadata()
        if args.field:
            print(result[args.field])
            return
    elif args.command == "crates":
        result = publication_order()
    else:
        from release_bundle import execute

        result = execute(args.command, args.directory)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
