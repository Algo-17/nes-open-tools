#!/usr/bin/env python3
"""Create architecture decision records, change their status, and rebuild the index.

Records live in docs/adr/; the format and rules are in golf/adr.py and
docs/adr/README.md. Every command that changes a record also regenerates the index.
"""

import argparse
import datetime
import sys
from pathlib import Path

from golf import adr


def _write_index(directory: Path, records: list[adr.Adr]) -> None:
    index = directory / adr.INDEX_NAME
    index.write_text(adr.render_index(index.read_text(), records))


def cmd_new(args: argparse.Namespace) -> int:
    records = adr.load_all(args.dir)
    title = args.title.strip()
    slug = adr.slug_from_title(title)
    if not title or not slug:
        print("error: TITLE needs at least one letter or digit", file=sys.stderr)
        return 2
    known = {r.number for r in records}
    missing = [n for n in args.supersedes if n not in known]
    if missing:
        print(f"error: no such ADRs to supersede: {missing}", file=sys.stderr)
        return 2

    number = adr.next_number(records)
    path = args.dir / f"{number:04d}-{slug}.md"
    path.write_text(
        adr.new_record(
            title,
            area=args.area,
            date=datetime.date.today(),
            drafted_by=args.drafted_by,
            revisit_when=args.revisit_when,
            permanent=args.permanent,
            supersedes=tuple(args.supersedes),
        )
    )
    _write_index(args.dir, adr.load_all(args.dir))
    print(path)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    records = adr.load_all(args.dir)
    changes = adr.set_status(records, args.number, args.status, datetime.date.today())
    for path, text in changes.items():
        path.write_text(text)
        print(f"updated {path}")
    _write_index(args.dir, adr.load_all(args.dir))
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    records = adr.load_all(args.dir)
    index = args.dir / adr.INDEX_NAME
    current = index.read_text()
    rendered = adr.render_index(current, records)
    if args.check:
        if rendered != current:
            print(f"{index} is out of date; run golf-adr index", file=sys.stderr)
            return 1
        return 0
    index.write_text(rendered)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    records = adr.load_all(args.dir)
    found = adr.problems(records)
    for problem in found:
        print(problem, file=sys.stderr)
    return 1 if found else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage architecture decision records in docs/adr/."
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=adr.ADR_DIR,
        help="record directory (default: docs/adr)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a proposed record with empty sections")
    new.add_argument("title", metavar="TITLE")
    new.add_argument("--area", required=True, choices=adr.AREAS)
    new.add_argument(
        "--supersedes",
        type=int,
        nargs="+",
        default=[],
        metavar="N",
        help="records this one replaces; they're marked superseded when it's accepted",
    )
    new.add_argument(
        "--revisit-when",
        default="",
        help="the observable condition that should reopen this decision",
    )
    new.add_argument(
        "--permanent",
        action="store_true",
        help="its effects can't be undone, e.g. something baked into released ROMs",
    )
    new.add_argument(
        "--drafted-by",
        default="jdharms",
        help="who wrote the draft (default: jdharms; Claude passes 'Claude')",
    )
    new.set_defaults(func=cmd_new)

    status = sub.add_parser(
        "status",
        help="set a record's status; accepting it supersedes what it replaces",
    )
    status.add_argument("number", type=int, metavar="N")
    status.add_argument(
        "status", choices=[s for s in adr.STATUSES if s != "superseded"]
    )
    status.set_defaults(func=cmd_status)

    index = sub.add_parser("index", help="regenerate the table in docs/adr/README.md")
    index.add_argument(
        "--check", action="store_true", help="exit 1 if the index is out of date"
    )
    index.set_defaults(func=cmd_index)

    check = sub.add_parser("check", help="report numbering and supersession problems")
    check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except adr.AdrError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
