"""Unit tests for the constant-acceleration green slope patch."""

import math

import pytest

from golf.core.patches.green_slope_physics import (
    MAGNITUDE_ORIGINAL,
    MAGNITUDE_PRG_OFFSET,
    SLOPE_END,
    SLOPE_LEN,
    SLOPE_ORIGINAL,
    SLOPE_PRG_OFFSET,
    SLOPE_START,
    GreenSlopeTuning,
    _build_code,
    green_slope_physics_patch,
)
from tests.prg_writer import PrgImageWriter


class MockRomWriter(PrgImageWriter):
    pass


def make_vanilla_like_rom() -> MockRomWriter:
    """A 256KB PRG image holding the vanilla bytes at every site this patch writes."""
    rom = MockRomWriter(bytes(16 * 0x4000))
    rom.write_prg(SLOPE_PRG_OFFSET, SLOPE_ORIGINAL)
    rom.write_prg(MAGNITUDE_PRG_OFFSET, MAGNITUDE_ORIGINAL)
    return rom


class TestLayout:
    def test_replaced_region_is_the_whole_routine(self):
        assert SLOPE_LEN == SLOPE_END - SLOPE_START == 112
        assert len(SLOPE_ORIGINAL) == SLOPE_LEN

    def test_code_fits_in_place(self):
        code = _build_code(GreenSlopeTuning())
        assert len(code) <= SLOPE_LEN

    def test_code_is_smaller_than_what_it_replaces(self):
        # The patch is meant to be strictly cheaper than the vanilla routine.
        assert len(_build_code(GreenSlopeTuning())) < SLOPE_LEN

    def test_code_ends_by_rejoining_the_vanilla_tail(self):
        # $B245 is reached only by fall-through in vanilla, so the replacement
        # has to jump there explicitly.
        code = _build_code(GreenSlopeTuning())
        assert bytes([0x4C, SLOPE_END & 0xFF, SLOPE_END >> 8]) in code

    def test_oversized_strength_still_fits(self):
        # Strength is baked into the table, not the code, so the code size is
        # independent of tuning.
        big = _build_code(GreenSlopeTuning(strength=80, friction=255))
        assert len(big) == len(_build_code(GreenSlopeTuning()))

    def test_friction_acts_on_one_axis_per_frame(self):
        """Per-axis constant friction caps break on a cardinal slope at
        `friction`, because the fall-line axis starts from zero. Only one
        SubAxis and one AddAxis call site may take the friction constant."""
        code = _build_code(GreenSlopeTuning(strength=30, friction=41))
        assert code.count(bytes([0xA9, 41])) == 1  # one LDA #friction

    def test_rest_test_precedes_any_acceleration(self):
        """Without it the slope creeps a resting ball and it never satisfies
        LD_B3BF_CheckStopped. The BEQ to the exit must come before the
        friction constant is loaded."""
        code = _build_code(GreenSlopeTuning(strength=30, friction=41))
        assert code.index(bytes([0x05, 0x00, 0xF0])) < code.index(bytes([0xA9, 41]))


class TestMagnitudeTable:
    def test_shape_matches_vanilla(self):
        table = GreenSlopeTuning().magnitude_table()
        assert len(table) == len(MAGNITUDE_ORIGINAL)
        assert table[0] == 0  # the zero component a cardinal tile uses

    def test_cardinals_keep_the_vanilla_1_2_3_ratio(self):
        table = GreenSlopeTuning(strength=30, friction=40).magnitude_table()
        gentle, moderate, steep = table[1], table[3], table[5]
        assert (gentle, moderate, steep) == (10, 20, 30)

    def test_diagonal_resultant_matches_its_cardinal(self):
        """Vanilla stores the full magnitude on both axes, so diagonals come out
        sqrt(2) too strong. Each component should be magnitude/sqrt(2)."""
        table = GreenSlopeTuning().magnitude_table()
        for cardinal_index, diagonal_index in ((1, 2), (3, 4), (5, 6)):
            cardinal = table[cardinal_index]
            resultant = table[diagonal_index] * math.sqrt(2)
            assert abs(resultant - cardinal) < 1.0

    def test_vanilla_diagonals_are_not_corrected(self):
        # Guards the premise: in vanilla the diagonal entry is ~= the cardinal.
        for cardinal_index, diagonal_index in ((1, 2), (3, 4), (5, 6)):
            cardinal = MAGNITUDE_ORIGINAL[cardinal_index]
            diagonal = MAGNITUDE_ORIGINAL[diagonal_index]
            assert abs(diagonal - cardinal) <= 1

    def test_no_slope_class_truncates_to_zero(self):
        """A class that rounds to 0 would silently make those tiles flat."""
        table = GreenSlopeTuning(strength=1, friction=2).magnitude_table()
        assert all(value > 0 for value in table[1:])


class TestTuningValidation:
    def test_friction_must_exceed_strength(self):
        # Otherwise the ball reaches a terminal rolling speed and never trips
        # LD_B3BF_CheckStopped.
        with pytest.raises(ValueError, match="must exceed strength"):
            GreenSlopeTuning(strength=30, friction=30)

    def test_friction_must_fit_in_a_byte(self):
        # It is assembled as an immediate operand.
        with pytest.raises(ValueError, match="fit in a byte"):
            GreenSlopeTuning(strength=80, friction=300)

    def test_strength_range(self):
        with pytest.raises(ValueError, match="strength must be"):
            GreenSlopeTuning(strength=0, friction=10)

    def test_defaults_are_valid(self):
        GreenSlopeTuning()


class TestPatchApplication:
    def test_applies_to_a_vanilla_rom(self):
        rom = make_vanilla_like_rom()
        patch = green_slope_physics_patch()
        assert patch.can_apply(rom)
        assert not patch.is_applied(rom)
        patch.apply(rom)
        assert patch.is_applied(rom)

    def test_is_idempotent(self):
        rom = make_vanilla_like_rom()
        patch = green_slope_physics_patch()
        patch.apply(rom)
        before = rom.read_prg(SLOPE_PRG_OFFSET, SLOPE_LEN)
        patch.apply(rom)
        assert rom.read_prg(SLOPE_PRG_OFFSET, SLOPE_LEN) == before

    def test_refuses_an_unexpected_rom(self):
        rom = make_vanilla_like_rom()
        rom.write_prg(SLOPE_PRG_OFFSET, bytes([0xAB] * 8))
        assert not green_slope_physics_patch().can_apply(rom)

    def test_leaves_the_vanilla_tail_alone(self):
        rom = make_vanilla_like_rom()
        green_slope_physics_patch().apply(rom)
        code_len = len(_build_code(GreenSlopeTuning()))
        tail = rom.read_prg(SLOPE_PRG_OFFSET + code_len, SLOPE_LEN - code_len)
        assert tail == SLOPE_ORIGINAL[code_len:]

    def test_tuning_reaches_the_rom(self):
        rom = make_vanilla_like_rom()
        green_slope_physics_patch(strength=45, friction=60).apply(rom)
        table = rom.read_prg(MAGNITUDE_PRG_OFFSET, len(MAGNITUDE_ORIGINAL))
        assert table[5] == 45
        assert bytes([0xA9, 60]) in rom.read_prg(SLOPE_PRG_OFFSET, SLOPE_LEN)
