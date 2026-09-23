"""Architecture decision records: parsing, checking, the index and new records.

An ADR is `docs/adr/NNNN-slug.md`, a trimmed-down MADR record:

    +++
    status = "proposed"
    date = 2026-09-23
    area = "patches"
    permanent = false
    revisit_when = "Multi-course generation is scheduled"
    drafted_by = "Claude"
    supersedes = []
    +++

    # Title

    ## Context
    ## Decision
    ## Rejected alternatives
    ## Consequences
    ## Sources

The number and slug come from the filename; the title is the H1. `superseded_by`
appears in the frontmatter only once a later ADR that supersedes this one is accepted.
A proposed ADR may leave sections empty (HTML comments don't count as content); any
other status needs every section filled in and must say when to revisit it. A rejected
record matters only for its reasons, so it's held to the same rule.

`docs/adr/README.md` holds the index table between two marker comments. It is
generated from the records by `render_index`, never edited by hand.
"""

import datetime
import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = REPO_ROOT / "docs" / "adr"
INDEX_NAME = "README.md"

FILENAME = re.compile(r"(\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md")
#: How code and docs cite a record: "ADR" and its four-digit number.
CITATION = re.compile(r"\bADR (\d{4})\b")

STATUSES = ("proposed", "accepted", "rejected", "deprecated", "superseded")
#: Statuses a record reaches by decision; each requires every section filled in.
DECIDED = ("accepted", "rejected", "deprecated", "superseded")
AREAS = ("rom", "patches", "qr", "randomizer", "site", "deploy", "tooling")
SECTIONS = ("Context", "Decision", "Rejected alternatives", "Consequences", "Sources")

INDEX_START = "<!-- adr-index:start -->"
INDEX_END = "<!-- adr-index:end -->"

_REQUIRED = {
    "status": str,
    "date": datetime.date,
    "area": str,
    "permanent": bool,
    "revisit_when": str,
    "drafted_by": str,
    "supersedes": list,
}
_OPTIONAL = {"superseded_by": int}
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

SECTION_HINTS = {
    "Context": "What forced a decision: the problem, the constraints, what was known.",
    "Decision": "What was decided, stated plainly enough to check code against.",
    "Rejected alternatives": "Each option not taken, and why.",
    "Consequences": "What this makes easier, harder, or impossible from now on.",
    "Sources": "Where the decision was made: docs, code, and sessions by date and ID.",
}


class AdrError(ValueError):
    """A record that can't be parsed, or a change the records don't allow."""


@dataclass(frozen=True)
class Adr:
    number: int
    slug: str
    path: Path
    title: str
    status: str
    date: datetime.date
    area: str
    permanent: bool
    revisit_when: str
    drafted_by: str
    supersedes: tuple[int, ...]
    superseded_by: int | None
    #: Section heading -> body, with HTML comments removed and whitespace stripped.
    sections: dict[str, str]

    @property
    def label(self) -> str:
        return f"ADR {self.number:04d}"


def split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter, body) of a record; the frontmatter excludes its `+++` lines."""
    lines = text.split("\n")
    if not lines or lines[0] != "+++":
        raise AdrError("must start with a +++ frontmatter line")
    try:
        end = lines.index("+++", 1)
    except ValueError:
        raise AdrError("frontmatter has no closing +++ line") from None
    return "\n".join(lines[1:end]), "\n".join(lines[end + 1 :])


def parse(path: Path) -> Adr:
    """Read one record, checking everything that doesn't depend on other records."""
    try:
        return _parse(path)
    except AdrError as error:
        raise AdrError(f"{path.name}: {error}") from None


def _parse(path: Path) -> Adr:
    match = FILENAME.fullmatch(path.name)
    if not match:
        raise AdrError("filename must be NNNN-lowercase-slug.md")
    front_text, body = split_frontmatter(path.read_text())
    try:
        front = tomllib.loads(front_text)
    except tomllib.TOMLDecodeError as error:
        raise AdrError(f"frontmatter is not valid TOML: {error}") from None

    unknown = set(front) - set(_REQUIRED) - set(_OPTIONAL)
    if unknown:
        raise AdrError(f"unknown frontmatter keys: {sorted(unknown)}")
    for key in _REQUIRED:
        if key not in front:
            raise AdrError(f"frontmatter is missing {key!r}")
    for key, kind in {**_REQUIRED, **_OPTIONAL}.items():
        # bool is an int subclass, so check it explicitly
        if key in front and (
            not isinstance(front[key], kind)
            or (kind is int and isinstance(front[key], bool))
        ):
            raise AdrError(f"{key!r} must be a {kind.__name__}")
    if front["status"] not in STATUSES:
        raise AdrError(f"status must be one of {STATUSES}")
    if front["area"] not in AREAS:
        raise AdrError(f"area must be one of {AREAS}")
    if not all(
        isinstance(n, int) and not isinstance(n, bool) for n in front["supersedes"]
    ):
        raise AdrError("'supersedes' must be a list of ADR numbers")

    title, sections = _parse_body(body)
    adr = Adr(
        number=int(match.group(1)),
        slug=match.group(2),
        path=path,
        title=title,
        status=front["status"],
        date=front["date"],
        area=front["area"],
        permanent=front["permanent"],
        revisit_when=front["revisit_when"].strip(),
        drafted_by=front["drafted_by"].strip(),
        supersedes=tuple(front["supersedes"]),
        superseded_by=front.get("superseded_by"),
        sections=sections,
    )
    if adr.status in DECIDED:
        empty = [name for name, content in sections.items() if not content]
        if empty:
            raise AdrError(f"a {adr.status} record needs content in {empty}")
        if not adr.revisit_when:
            raise AdrError(f"a {adr.status} record needs revisit_when")
    return adr


def _parse_body(body: str) -> tuple[str, dict[str, str]]:
    lines = body.strip("\n").split("\n")
    if not lines or not lines[0].startswith("# "):
        raise AdrError("the body must start with a '# Title' line")
    title = lines[0][2:].strip()
    if not title:
        raise AdrError("the title is empty")

    headings: list[str] = []
    chunks: list[list[str]] = []
    fenced = False
    for line in lines[1:]:
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if fenced or line.lstrip().startswith("```"):
            if not chunks and line.strip():
                raise AdrError("text between the title and the first section")
            if chunks:
                chunks[-1].append(line)
            continue
        if line.startswith("# "):
            raise AdrError("only one '# ' heading is allowed")
        if line.startswith("## "):
            headings.append(line[3:].strip())
            chunks.append([])
        elif chunks:
            chunks[-1].append(line)
        elif line.strip():
            raise AdrError("text between the title and the first section")
    if tuple(headings) != SECTIONS:
        raise AdrError(f"sections must be exactly {list(SECTIONS)}, in that order")
    sections = {
        heading: _COMMENT.sub("", "\n".join(chunk)).strip()
        for heading, chunk in zip(headings, chunks, strict=True)
    }
    return title, sections


def record_paths(directory: Path = ADR_DIR) -> list[Path]:
    """Every record file in the directory: all Markdown except the index."""
    return sorted(p for p in directory.glob("*.md") if p.name != INDEX_NAME)


def load_all(directory: Path = ADR_DIR) -> list[Adr]:
    """Every record, parsed, in number order. Raises on the first bad file."""
    return sorted(
        (parse(path) for path in record_paths(directory)), key=lambda a: a.number
    )


def problems(adrs: list[Adr]) -> list[str]:
    """What's wrong across a set of records: numbering and supersession links."""
    found: list[str] = []
    by_number: dict[int, Adr] = {}
    for adr in adrs:
        if adr.number in by_number:
            found.append(
                f"{adr.path.name} and {by_number[adr.number].path.name} share a number"
            )
        by_number.setdefault(adr.number, adr)

    expected = list(range(1, len(by_number) + 1))
    if sorted(by_number) != expected:
        found.append(f"numbers must run 1-{len(by_number)} with no gaps")

    for adr in adrs:
        for target in adr.supersedes:
            if target == adr.number:
                found.append(f"{adr.label} supersedes itself")
            elif target not in by_number:
                found.append(f"{adr.label} supersedes missing ADR {target:04d}")
            elif (
                adr.status == "accepted"
                and by_number[target].superseded_by != adr.number
            ):
                found.append(
                    f"{adr.label} is accepted and supersedes ADR {target:04d}, "
                    f"which must be marked superseded_by = {adr.number}"
                )

        if (adr.status == "superseded") != (adr.superseded_by is not None):
            found.append(
                f"{adr.label}: status 'superseded' and superseded_by go together"
            )
        if adr.superseded_by is not None:
            successor = by_number.get(adr.superseded_by)
            if successor is None:
                found.append(
                    f"{adr.label} is superseded by missing ADR {adr.superseded_by:04d}"
                )
            elif adr.number not in successor.supersedes:
                found.append(
                    f"{adr.label} is superseded by {successor.label}, "
                    "which doesn't list it in supersedes"
                )
            elif successor.status != "accepted":
                found.append(
                    f"{adr.label} is superseded by {successor.label}, "
                    "which isn't accepted"
                )
    return found


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ") or "-"


def index_table(adrs: list[Adr]) -> str:
    """The index's Markdown table, one row per record."""
    rows = [
        "| ADR | Title | Area | Status | Permanent | Revisit when |",
        "|-----|-------|------|--------|-----------|--------------|",
    ]
    for adr in adrs:
        status = adr.status
        if adr.superseded_by is not None:
            status += (
                f" by [{adr.superseded_by:04d}]({_filename(adrs, adr.superseded_by)})"
            )
        rows.append(
            f"| [{adr.number:04d}]({adr.path.name}) | {_cell(adr.title)} "
            f"| {adr.area} | {status} | {'yes' if adr.permanent else ''} "
            f"| {_cell(adr.revisit_when)} |"
        )
    return "\n".join(rows)


def _filename(adrs: list[Adr], number: int) -> str:
    return next((a.path.name for a in adrs if a.number == number), "")


def render_index(index_text: str, adrs: list[Adr]) -> str:
    """The index file's text with the table between the markers regenerated."""
    start = index_text.find(INDEX_START)
    end = index_text.find(INDEX_END)
    if start < 0 or end < start:
        raise AdrError(f"the index needs {INDEX_START} and {INDEX_END} markers")
    head = index_text[: start + len(INDEX_START)]
    return f"{head}\n{index_table(adrs)}\n{index_text[end:]}"


def slug_from_title(title: str) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")


def next_number(adrs: list[Adr]) -> int:
    return max((a.number for a in adrs), default=0) + 1


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def new_record(
    title: str,
    *,
    area: str,
    date: datetime.date,
    drafted_by: str,
    revisit_when: str = "",
    permanent: bool = False,
    supersedes: tuple[int, ...] = (),
) -> str:
    """A proposed record with empty sections, each carrying a hint comment."""
    if area not in AREAS:
        raise AdrError(f"area must be one of {AREAS}")
    front = [
        "+++",
        'status = "proposed"',
        f"date = {date.isoformat()}",
        f"area = {_toml_string(area)}",
        f"permanent = {str(permanent).lower()}",
        f"revisit_when = {_toml_string(revisit_when)}",
        f"drafted_by = {_toml_string(drafted_by)}",
        f"supersedes = [{', '.join(str(n) for n in supersedes)}]",
        "+++",
        "",
        f"# {title}",
    ]
    body = [f"\n## {name}\n\n<!-- {SECTION_HINTS[name]} -->" for name in SECTIONS]
    return "\n".join(front) + "\n" + "\n".join(body) + "\n"


def set_frontmatter(text: str, key: str, literal: str) -> str:
    """Set one frontmatter key to a TOML literal, keeping every other line as is."""
    front, body = split_frontmatter(text)
    lines = front.split("\n")
    pattern = re.compile(rf"{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key} = {literal}"
            break
    else:
        lines.append(f"{key} = {literal}")
    return "+++\n" + "\n".join(lines) + "\n+++\n" + body


def set_status(
    adrs: list[Adr], number: int, status: str, today: datetime.date
) -> dict[Path, str]:
    """New text for every file a status change touches.

    Accepting a record also marks each record it supersedes as superseded. The
    'superseded' status can only be reached that way.
    """
    by_number = {a.number: a for a in adrs}
    adr = by_number.get(number)
    if adr is None:
        raise AdrError(f"there is no ADR {number:04d}")
    if status == "superseded":
        raise AdrError("a record becomes superseded when its successor is accepted")
    if status not in STATUSES:
        raise AdrError(f"status must be one of {STATUSES}")
    if adr.status == "superseded":
        raise AdrError(f"{adr.label} is superseded; write a new record instead")

    if status in DECIDED:
        empty = [name for name, content in adr.sections.items() if not content]
        if empty:
            raise AdrError(f"{adr.label} needs content in {empty} first")
        if not adr.revisit_when:
            raise AdrError(f"{adr.label} needs revisit_when first")

    changes: dict[Path, str] = {}
    text = set_frontmatter(adr.path.read_text(), "status", _toml_string(status))
    changes[adr.path] = set_frontmatter(text, "date", today.isoformat())
    if status == "accepted":
        for target in adr.supersedes:
            old = by_number.get(target)
            if old is None:
                raise AdrError(f"{adr.label} supersedes missing ADR {target:04d}")
            text = set_frontmatter(old.path.read_text(), "status", '"superseded"')
            text = set_frontmatter(text, "date", today.isoformat())
            changes[old.path] = set_frontmatter(text, "superseded_by", str(number))
    return changes
