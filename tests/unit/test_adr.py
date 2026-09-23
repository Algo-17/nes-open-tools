"""golf/adr.py and the golf-adr CLI, on records in a temporary directory."""

import datetime
import subprocess
import sys
from pathlib import Path

import pytest

from golf import adr

ROOT = Path(__file__).resolve().parents[2]
TODAY = datetime.date(2026, 9, 23)
INDEX = f"# Records\n\n{adr.INDEX_START}\n{adr.INDEX_END}\n"


def _filled(text: str) -> str:
    """A record with every section given one line of content."""
    for name in adr.SECTIONS:
        text = text.replace(f"<!-- {adr.SECTION_HINTS[name]} -->", f"{name} text.")
    return text


def _write(
    directory: Path, number: int, *, filled: bool = True, revisit: str = "never", **kw
) -> Path:
    text = adr.new_record(
        f"Decision {number}",
        area="patches",
        date=TODAY,
        drafted_by="Claude",
        revisit_when=revisit,
        **kw,
    )
    path = directory / f"{number:04d}-decision-{number}.md"
    path.write_text(_filled(text) if filled else text)
    return path


@pytest.fixture
def adr_dir(tmp_path: Path) -> Path:
    (tmp_path / adr.INDEX_NAME).write_text(INDEX)
    return tmp_path


def _accept(directory: Path, number: int) -> None:
    for path, text in adr.set_status(
        adr.load_all(directory), number, "accepted", TODAY
    ).items():
        path.write_text(text)


# -- Parsing


def test_a_new_record_parses_as_proposed_with_empty_sections(adr_dir):
    record = adr.parse(_write(adr_dir, 1, filled=False, revisit=""))
    assert record.number == 1
    assert record.slug == "decision-1"
    assert record.title == "Decision 1"
    assert record.status == "proposed"
    assert record.date == TODAY
    assert record.drafted_by == "Claude"
    assert record.supersedes == ()
    assert record.superseded_by is None
    assert list(record.sections) == list(adr.SECTIONS)
    assert all(content == "" for content in record.sections.values())


def test_hint_comments_are_not_content(adr_dir):
    text = adr.new_record("T", area="rom", date=TODAY, drafted_by="x")
    assert "<!--" in text
    path = adr_dir / "0001-t.md"
    path.write_text(text)
    assert adr.parse(path).sections["Context"] == ""


@pytest.mark.parametrize(
    ("replace", "by", "message"),
    [
        ('status = "proposed"', 'status = "maybe"', "status must be one of"),
        ('area = "patches"', 'area = "nowhere"', "area must be one of"),
        ("permanent = false", 'permanent = "no"', "'permanent' must be a bool"),
        ("supersedes = []", 'supersedes = ["x"]', "list of ADR numbers"),
        ("supersedes = []", "supersedes = []\nsuperseded = 2", "unknown frontmatter"),
        ('drafted_by = "Claude"\n', "", "missing 'drafted_by'"),
        ("## Consequences", "## Outcome", "sections must be exactly"),
        ("# Decision 1", "# Decision 1\n\n# Another", "only one '# ' heading"),
    ],
)
def test_malformed_records_are_rejected(adr_dir, replace, by, message):
    path = _write(adr_dir, 1)
    path.write_text(path.read_text().replace(replace, by, 1))
    with pytest.raises(adr.AdrError, match=message):
        adr.parse(path)


def test_a_bad_filename_is_rejected(adr_dir):
    path = _write(adr_dir, 1)
    renamed = path.rename(adr_dir / "1-Decision.md")
    with pytest.raises(adr.AdrError, match="filename"):
        adr.parse(renamed)


def test_a_heading_inside_a_code_block_is_content(adr_dir):
    path = _write(adr_dir, 1)
    path.write_text(
        path.read_text().replace("Context text.", "```bash\n# a comment\n```")
    )
    assert "# a comment" in adr.parse(path).sections["Context"]


@pytest.mark.parametrize("status", ["accepted", "rejected", "deprecated"])
def test_a_decided_record_must_be_filled_in(adr_dir, status):
    path = _write(adr_dir, 1, filled=False)
    path.write_text(path.read_text().replace('"proposed"', f'"{status}"'))
    with pytest.raises(adr.AdrError, match="needs content"):
        adr.parse(path)


@pytest.mark.parametrize("status", ["accepted", "rejected", "deprecated"])
def test_a_decided_record_must_say_when_to_revisit(adr_dir, status):
    path = _write(adr_dir, 1, revisit="")
    path.write_text(path.read_text().replace('"proposed"', f'"{status}"'))
    with pytest.raises(adr.AdrError, match="revisit_when"):
        adr.parse(path)


# -- Problems across records


def test_numbers_must_run_without_gaps(adr_dir):
    _write(adr_dir, 1)
    _write(adr_dir, 3)
    assert any("no gaps" in p for p in adr.problems(adr.load_all(adr_dir)))


def test_two_records_cannot_share_a_number(adr_dir):
    _write(adr_dir, 1)
    other = adr_dir / "0001-another.md"
    other.write_text(_write(adr_dir, 2).read_text())
    (adr_dir / "0002-decision-2.md").unlink()
    assert any("share a number" in p for p in adr.problems(adr.load_all(adr_dir)))


def test_superseding_a_missing_record_is_a_problem(adr_dir):
    _write(adr_dir, 1, supersedes=(5,))
    assert any("supersedes missing" in p for p in adr.problems(adr.load_all(adr_dir)))


def test_an_accepted_successor_must_be_recorded_on_its_predecessor(adr_dir):
    _write(adr_dir, 1)
    path = _write(adr_dir, 2, supersedes=(1,))
    path.write_text(path.read_text().replace('"proposed"', '"accepted"'))
    found = adr.problems(adr.load_all(adr_dir))
    assert any(f"superseded_by = {2}" in p for p in found)


def test_a_proposed_successor_leaves_its_predecessor_alone(adr_dir):
    _write(adr_dir, 1)
    _write(adr_dir, 2, supersedes=(1,))
    assert adr.problems(adr.load_all(adr_dir)) == []


# -- Status changes


def test_accepting_a_successor_supersedes_its_predecessor(adr_dir):
    _write(adr_dir, 1)
    _accept(adr_dir, 1)
    _write(adr_dir, 2, supersedes=(1,))
    _accept(adr_dir, 2)
    first, second = adr.load_all(adr_dir)
    assert second.status == "accepted"
    assert first.status == "superseded"
    assert first.superseded_by == 2
    assert adr.problems([first, second]) == []


def test_a_status_change_keeps_the_rest_of_the_record(adr_dir):
    path = _write(adr_dir, 1)
    before = path.read_text()
    _accept(adr_dir, 1)
    after = path.read_text()
    assert after.replace('"accepted"', '"proposed"') == before


def test_superseded_cannot_be_set_directly(adr_dir):
    _write(adr_dir, 1)
    with pytest.raises(adr.AdrError, match="successor is accepted"):
        adr.set_status(adr.load_all(adr_dir), 1, "superseded", TODAY)


@pytest.mark.parametrize("status", ["accepted", "rejected"])
def test_an_unfilled_record_cannot_be_decided(adr_dir, status):
    _write(adr_dir, 1, filled=False)
    with pytest.raises(adr.AdrError, match="needs content"):
        adr.set_status(adr.load_all(adr_dir), 1, status, TODAY)


# -- The index


def test_the_index_lists_every_record(adr_dir):
    _write(adr_dir, 1)
    _write(adr_dir, 2, permanent=True)
    text = adr.render_index(INDEX, adr.load_all(adr_dir))
    assert (
        "[0001](0001-decision-1.md) | Decision 1 | patches | proposed |  | never |"
        in (text)
    )
    assert "| proposed | yes |" in text
    assert text.startswith("# Records\n")
    assert text.endswith(f"{adr.INDEX_END}\n")
    # rendering twice changes nothing
    assert adr.render_index(text, adr.load_all(adr_dir)) == text


def test_the_index_links_a_superseded_record_to_its_successor(adr_dir):
    _write(adr_dir, 1)
    _accept(adr_dir, 1)
    _write(adr_dir, 2, supersedes=(1,))
    _accept(adr_dir, 2)
    text = adr.index_table(adr.load_all(adr_dir))
    assert "superseded by [0002](0002-decision-2.md)" in text


def test_an_index_without_markers_is_rejected():
    with pytest.raises(adr.AdrError, match="markers"):
        adr.render_index("# Records\n", [])


# -- The CLI


def run(directory: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.dev.adr", "--dir", str(directory), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_new_creates_the_next_record_and_updates_the_index(adr_dir):
    _write(adr_dir, 1)
    assert run(adr_dir, "new", "Ship it!", "--area", "site").returncode == 0
    record = adr.parse(adr_dir / "0002-ship-it.md")
    assert record.title == "Ship it!"
    assert record.area == "site"
    assert record.drafted_by == "jdharms"
    assert "0002-ship-it.md" in (adr_dir / adr.INDEX_NAME).read_text()


def test_new_refuses_to_supersede_a_missing_record(adr_dir):
    result = run(adr_dir, "new", "T", "--area", "rom", "--supersedes", "4")
    assert result.returncode == 2
    assert "no such ADRs" in result.stderr


def test_status_accepts_and_the_index_follows(adr_dir):
    _write(adr_dir, 1)
    assert run(adr_dir, "status", "1", "accepted").returncode == 0
    assert adr.parse(adr_dir / "0001-decision-1.md").status == "accepted"
    assert "| accepted |" in (adr_dir / adr.INDEX_NAME).read_text()


def test_index_check_reports_a_stale_index(adr_dir):
    _write(adr_dir, 1)
    assert run(adr_dir, "index", "--check").returncode == 1
    assert run(adr_dir, "index").returncode == 0
    assert run(adr_dir, "index", "--check").returncode == 0


def test_a_refused_status_change_is_an_error_not_a_traceback(adr_dir):
    _write(adr_dir, 1, filled=False)
    result = run(adr_dir, "status", "1", "accepted")
    assert result.returncode == 1
    assert "needs content" in result.stderr
