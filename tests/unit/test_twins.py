"""Unit tests for the family candidates read out of hole data.

Signatures are built directly rather than from hole files: `tests/synthetic_holes.py`
gives every hole the same greens, which is the one thing these tests need to vary.
"""

from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.twins import (
    Candidate,
    HoleSignature,
    candidates,
    suggested_label,
    terrain_similarity,
)


def sig(lineage, greens="a", terrain=None, par=4, distance=400, **kwargs):
    rows = terrain if terrain is not None else [[1, 2, 3, 4]] * 4
    return HoleSignature(
        lineage=lineage,
        par=par,
        distance=distance,
        greens_hash=greens,
        terrain=tuple(tuple(row) for row in rows),
        **kwargs,
    )


def lineages(found: list[Candidate]) -> list[tuple[str, ...]]:
    return [one.lineages for one in found]


def test_identical_greens_pair_up():
    holes = [sig("nes_uk/01"), sig("jp_japan/01"), sig("nes_us/05", greens="b")]
    found = candidates(holes, CurationSnapshot())
    assert lineages(found) == [("jp_japan/01", "nes_uk/01")]
    assert found[0].greens_match
    assert found[0].terrain_score == 1.0


def test_a_greens_layout_shared_by_three_is_one_group():
    holes = [sig("nes_uk/01"), sig("jp_japan/01"), sig("jp_uk/07")]
    assert lineages(candidates(holes, CurationSnapshot())) == [
        ("jp_japan/01", "jp_uk/07", "nes_uk/01")
    ]


def test_a_terrain_near_match_pairs_up_despite_different_greens():
    near = [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 9]]
    holes = [sig("nes_uk/01", greens="a"), sig("jp_japan/01", greens="b", terrain=near)]
    found = candidates(holes, CurationSnapshot())
    assert lineages(found) == [("jp_japan/01", "nes_uk/01")]
    assert not found[0].greens_match
    assert 0.9 < found[0].terrain_score < 1.0


def test_unrelated_terrain_is_not_a_candidate():
    holes = [
        sig("nes_uk/01", greens="a"),
        sig("jp_japan/01", greens="b", terrain=[[9, 9, 9, 9]] * 4),
    ]
    assert candidates(holes, CurationSnapshot()) == []


def test_greens_groups_rank_above_terrain_only_pairs():
    near = [[1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 4], [1, 2, 3, 9]]
    holes = [
        sig("nes_uk/01"),
        sig("jp_japan/01"),
        sig("nes_us/05", greens="b"),
        sig("jp_uk/07", greens="c", terrain=near),
    ]
    assert lineages(candidates(holes, CurationSnapshot())) == [
        ("jp_japan/01", "nes_uk/01"),
        ("jp_uk/07", "nes_us/05"),
    ]


def test_holes_already_in_a_family_are_left_out():
    holes = [sig("nes_uk/01"), sig("jp_japan/01")]
    curation = CurationSnapshot.from_json({"nes_uk/01": {"family": "nes_uk_01"}})
    assert candidates(holes, curation) == []
    assert lineages(candidates(holes, curation, include_familied=True)) == [
        ("jp_japan/01", "nes_uk/01")
    ]


def test_a_taller_hole_scores_below_an_identical_one():
    tall = sig("jp_japan/01", greens="b", terrain=[[1, 2, 3, 4]] * 6)
    assert terrain_similarity(sig("nes_uk/01", greens="a"), tall) < 1.0


def test_suggested_label_prefers_the_nes_open_hole():
    assert suggested_label(["jp_japan/01", "nes_uk/01"]) == "nes_uk_01"
    assert suggested_label(["jp_australia/06", "jp_japan/01"]) == "jp_australia_06"


def test_a_vanilla_hole_carries_its_rangefinder_link():
    assert sig("nes_uk/01", course="uk", hole=1).rangefinder_query == "course=uk&hole=1"
    assert sig("dharms/cliffside").rangefinder_query is None
