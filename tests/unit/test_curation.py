"""Unit tests for curation records and snapshots."""

import pytest

from golf.randomizer.catalog import Catalog
from golf.randomizer.curation import (
    DEFAULT_CURATION,
    CurationError,
    CurationSnapshot,
    HoleCuration,
)


def test_uncurated_holes_get_the_default_record():
    snapshot = CurationSnapshot.from_json({"nes_uk/01": {"tags": ["dogleg"]}})
    assert snapshot.for_hole("nes_us/07") == HoleCuration()
    assert HoleCuration().drawable


def test_records_apply_to_every_version_of_a_lineage():
    snapshot = CurationSnapshot.from_json(
        {"dharms/cliffside": {"family": "cliffs", "drawable": False}}
    )
    assert snapshot.for_hole("dharms/cliffside@3") == snapshot.for_hole(
        "dharms/cliffside"
    )
    assert snapshot.for_hole("dharms/cliffside@3").family == "cliffs"


def test_rejects_versioned_keys():
    with pytest.raises(CurationError, match="no @version"):
        CurationSnapshot.from_json({"nes_uk/01@2": {}})


@pytest.mark.parametrize(
    "record",
    [
        {"tag": ["dogleg"]},
        {"tags": "dogleg"},
        {"drawable": "no"},
        {"family": "Not A Slug"},
        {"display_name": 7},
        ["dogleg"],
    ],
)
def test_rejects_malformed_records(record):
    with pytest.raises(CurationError):
        CurationSnapshot.from_json({"nes_uk/01": record})


def test_stamp_depends_on_content_not_key_or_tag_order():
    a = CurationSnapshot.from_json(
        {"a/b": {"tags": ["x", "y"], "family": "f"}, "c/d": {}}
    )
    b = CurationSnapshot.from_json(
        {"c/d": {}, "a/b": {"family": "f", "tags": ["y", "x"]}}
    )
    c = CurationSnapshot.from_json({"a/b": {"tags": ["x"], "family": "f"}, "c/d": {}})
    assert a.stamp == b.stamp != c.stamp


def test_families_group_lineages_by_label():
    snapshot = CurationSnapshot.from_json(
        {
            "nes_uk/01": {"family": "nes_uk_01"},
            "jp_japan/01": {"family": "nes_uk_01"},
            "nes_us/02": {},
        }
    )
    assert snapshot.families() == {"nes_uk_01": ["jp_japan/01", "nes_uk/01"]}


def test_round_trip():
    data = {
        "a/b": {
            "tags": ["x"],
            "drawable": False,
            "family": "f",
            "display_name": "Cliffs",
        }
    }
    assert CurationSnapshot.from_json(data).to_json() == data


def test_checked_in_curation_names_only_catalog_lineages():
    snapshot = CurationSnapshot.load()
    assert DEFAULT_CURATION.exists()
    assert snapshot.unknown_lineages(Catalog.load()) == []


def test_save_round_trips_through_load(tmp_path):
    path = tmp_path / "nested" / "curation.json"
    snapshot = CurationSnapshot.from_json(
        {"nes_uk/01": {"family": "nes_uk_01", "tags": ["dogleg"], "drawable": False}}
    )
    snapshot.save(path)
    assert CurationSnapshot.load(path) == snapshot


def test_save_writes_one_line_per_record(tmp_path):
    path = tmp_path / "curation.json"
    CurationSnapshot.from_json(
        {"nes_uk/01": {"family": "f"}, "jp_japan/01": {"family": "f"}}
    ).save(path)
    assert path.read_text() == (
        '{\n  "jp_japan/01": {"family": "f"},\n  "nes_uk/01": {"family": "f"}\n}\n'
    )


def test_save_writes_an_empty_snapshot(tmp_path):
    path = tmp_path / "curation.json"
    CurationSnapshot().save(path)
    assert path.read_text() == "{}\n"
    assert CurationSnapshot.load(path) == CurationSnapshot()


def test_setting_a_family_keeps_the_rest_of_the_record():
    snapshot = CurationSnapshot.from_json(
        {"nes_uk/01": {"tags": ["dogleg"], "display_name": "Cliffs"}}
    )
    updated = snapshot.set_family(["nes_uk/01", "jp_japan/01"], "nes_uk_01")
    assert updated.families() == {"nes_uk_01": ["jp_japan/01", "nes_uk/01"]}
    assert updated.for_hole("nes_uk/01").tags == frozenset({"dogleg"})
    assert updated.for_hole("nes_uk/01").display_name == "Cliffs"


def test_setting_a_family_leaves_the_original_snapshot_alone():
    snapshot = CurationSnapshot()
    snapshot.set_family(["nes_uk/01"], "f")
    assert snapshot.holes == {}


def test_a_hole_is_in_at_most_one_family():
    snapshot = CurationSnapshot.from_json({"nes_uk/01": {"family": "first"}})
    with pytest.raises(CurationError, match="already in family 'first'"):
        snapshot.set_family(["nes_uk/01"], "second")
    assert snapshot.set_family(["nes_uk/01"], "second", move=True).families() == {
        "second": ["nes_uk/01"]
    }


def test_rejects_a_malformed_family_label():
    with pytest.raises(CurationError, match="must match"):
        CurationSnapshot().set_family(["nes_uk/01"], "Not A Slug")


def test_rejects_a_versioned_lineage():
    with pytest.raises(CurationError, match="is not a lineage"):
        CurationSnapshot().set_family(["nes_uk/01@2"], "f")


def test_clearing_the_last_field_drops_the_record():
    snapshot = CurationSnapshot.from_json({"nes_uk/01": {"family": "f"}})
    cleared = snapshot.clear_family(["nes_uk/01"])
    assert cleared.holes == {}
    assert cleared.to_json() == {}


def test_clearing_a_hole_in_no_family_names_it():
    with pytest.raises(CurationError, match="nes_uk/01 is in no family"):
        CurationSnapshot().clear_family(["nes_uk/01"])


def test_renaming_a_family_moves_every_member():
    snapshot = CurationSnapshot.from_json(
        {"nes_uk/01": {"family": "old"}, "jp_japan/01": {"family": "old"}}
    )
    assert snapshot.rename_family("old", "new").families() == {
        "new": ["jp_japan/01", "nes_uk/01"]
    }


def test_renaming_onto_an_existing_family_merges_them():
    snapshot = CurationSnapshot.from_json(
        {"nes_uk/01": {"family": "a"}, "jp_japan/01": {"family": "b"}}
    )
    assert snapshot.rename_family("a", "b").families() == {
        "b": ["jp_japan/01", "nes_uk/01"]
    }


def test_renaming_an_absent_family_is_an_error():
    with pytest.raises(CurationError, match="no family named 'nope'"):
        CurationSnapshot().rename_family("nope", "other")
