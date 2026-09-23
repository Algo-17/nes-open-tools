"""The architecture decision records in docs/adr/ are well formed and consistent.

Each record parses (golf/adr.py checks the frontmatter, the sections, and that decided
records are filled in), numbers run without gaps or collisions, supersession links
agree in both directions, the index table is current, and every "ADR NNNN" citation
anywhere in the tracked files names a record that exists.
"""

import subprocess
from pathlib import Path

from golf import adr

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".py", ".md", ".toml", ".html", ".js", ".css", ".jsonc", ".yml", ".sh"}


def test_every_record_parses():
    errors = []
    for path in adr.record_paths():
        try:
            adr.parse(path)
        except adr.AdrError as error:
            errors.append(str(error))
    assert not errors, "malformed ADRs:\n" + "\n".join(errors)


def test_records_are_consistent():
    found = adr.problems(adr.load_all())
    assert not found, "ADR problems:\n" + "\n".join(found)


def test_index_is_current():
    index = adr.ADR_DIR / adr.INDEX_NAME
    current = index.read_text()
    assert adr.render_index(current, adr.load_all()) == current, (
        "docs/adr/README.md is out of date; run `uv run golf-adr index`"
    )


def test_every_citation_names_a_record():
    numbers = {record.number for record in adr.load_all()}
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    broken = []
    for name in tracked:
        path = ROOT / name
        if path.suffix not in TEXT_SUFFIXES or not path.is_file():
            continue
        for match in adr.CITATION.finditer(path.read_text(errors="ignore")):
            if int(match.group(1)) not in numbers:
                broken.append(f"{name}: {match.group(0)}")
    assert not broken, "citations of ADRs that don't exist:\n" + "\n".join(broken)
