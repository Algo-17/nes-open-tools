"""Unit tests for the terrain-bottom threshold tables (docs/wram_expansion.md)."""

import pytest

from golf.core.patches.byte_patch import BytePatch
from golf.core.patches.wram_expansion import (
    TERRAIN_BOTTOM_TABLE_PATCHES,
    WRAM_EXPANSION_PATCH,
)
from golf.core.patches.wram_expansion.terrain_bottom_tables import (
    MAX_SCROLL_LIMIT,
    TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH,
    TERRAIN_BOTTOM_Y_HI_SBC_PATCH,
    TERRAIN_BOTTOM_Y_HI_TABLE,
    TERRAIN_BOTTOM_Y_LO_GROW_PATCH,
    TERRAIN_BOTTOM_Y_LO_TABLE,
    terrain_bottom_y,
)

# The fixed bank ($C000-$FFFF) is PRG bank 15, so CPU + $30000 is its offset.
FIXED_BANK_ORIGIN = 0x30000

# CPU $EFE2, where TerrainBottomYLo stays put and grows.
LO_TABLE_ADDR = 0xEFE2
# CPU $EFF6, the first byte of real code after the vanilla table pair.
CODE_AFTER_TABLES_ADDR = 0xEFF6
# CPU $E517, the first byte after the region the ViewOffsetTo* tables vacated.
VACATED_REGION_END_ADDR = 0xE517


@pytest.mark.parametrize("terrain_height", range(30, 62, 2))
def test_threshold_is_the_terrain_height_in_pixels(terrain_height):
    """Each entry is where the terrain ends, which is what the probe compares
    the ball's Y against."""
    scroll_limit = (terrain_height - 28) // 2
    assert terrain_bottom_y(scroll_limit) == terrain_height * 8


def test_tables_cover_every_reachable_scroll_limit():
    assert len(TERRAIN_BOTTOM_Y_LO_TABLE) == MAX_SCROLL_LIMIT + 1
    assert len(TERRAIN_BOTTOM_Y_HI_TABLE) == MAX_SCROLL_LIMIT + 1


@pytest.mark.parametrize("scroll_limit", range(1, MAX_SCROLL_LIMIT + 1))
def test_table_entries_split_the_threshold_low_high(scroll_limit):
    expected = terrain_bottom_y(scroll_limit)
    low = TERRAIN_BOTTOM_Y_LO_TABLE[scroll_limit]
    high = TERRAIN_BOTTOM_Y_HI_TABLE[scroll_limit]
    assert high << 8 | low == expected


def test_vanilla_entries_are_reproduced_exactly():
    """Indices 0-9 must still be the bytes the vanilla ROM ships, so the
    patch only ever adds entries."""
    assert TERRAIN_BOTTOM_Y_LO_TABLE[:10] == bytes(
        [0xF0, 0xF0, 0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70]
    )
    assert TERRAIN_BOTTOM_Y_HI_TABLE[:10] == bytes([0x00, 0x00] + [0x01] * 8)


def test_scroll_limit_11_is_no_longer_zero():
    """The regression: a 50-row hole (JP France 18) read $0000 off the end of
    both tables, so every ball position failed the on-the-terrain check."""
    assert terrain_bottom_y(11) == 50 * 8
    assert TERRAIN_BOTTOM_Y_LO_TABLE[11] == 0x90
    assert TERRAIN_BOTTOM_Y_HI_TABLE[11] == 0x01


def test_lo_grows_in_place_from_its_vanilla_base():
    """Lo's read site is never patched, so its base address must not move."""
    grown_start = TERRAIN_BOTTOM_Y_LO_GROW_PATCH.prg_offset - FIXED_BANK_ORIGIN
    assert grown_start == LO_TABLE_ADDR + 10
    assert TERRAIN_BOTTOM_Y_LO_GROW_PATCH.patched == TERRAIN_BOTTOM_Y_LO_TABLE[10:]


def test_lo_grow_stops_before_the_code_that_follows():
    """Lo's new tail lives in Hi's vacated space and must not reach $EFF6."""
    patch = TERRAIN_BOTTOM_Y_LO_GROW_PATCH
    end = patch.prg_offset - FIXED_BANK_ORIGIN + len(patch.patched)
    assert end <= CODE_AFTER_TABLES_ADDR


def test_hi_fits_the_region_the_view_offset_tables_vacated():
    patch = TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH
    end = patch.prg_offset - FIXED_BANK_ORIGIN + len(patch.patched)
    assert end <= VACATED_REGION_END_ADDR


def test_hi_read_site_points_at_the_relocated_table():
    """The SBC keeps its opcode and gains the new table's address."""
    opcode, low, high = TERRAIN_BOTTOM_Y_HI_SBC_PATCH.patched
    assert opcode == TERRAIN_BOTTOM_Y_HI_SBC_PATCH.original[0]
    assert high << 8 | low == (
        TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH.prg_offset - FIXED_BANK_ORIGIN
    )


def test_patches_are_in_the_composite():
    for patch in TERRAIN_BOTTOM_TABLE_PATCHES:
        assert patch in WRAM_EXPANSION_PATCH.patches


def test_no_two_wram_expansion_patches_write_the_same_byte():
    """The composite is one PatchStack step, so the stack's own overlap check
    never sees inside it."""
    owner: dict[int, str] = {}
    for patch in WRAM_EXPANSION_PATCH.patches:
        assert isinstance(patch, BytePatch)
        for offset in range(patch.prg_offset, patch.prg_offset + len(patch.patched)):
            assert offset not in owner, (
                f"{patch.name} overlaps {owner[offset]} at 0x{offset:X}"
            )
            owner[offset] = patch.name
