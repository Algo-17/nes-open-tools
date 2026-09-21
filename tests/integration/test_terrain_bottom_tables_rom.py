"""Integration tests: the terrain-bottom tables against the real vanilla ROM."""

from pathlib import Path

import pytest

from golf.core.patches import WRAM_EXPANSION_PATCH
from golf.core.patches.wram_expansion.terrain_bottom_tables import (
    MAX_SCROLL_LIMIT,
    TERRAIN_BOTTOM_TABLE_PATCHES,
    TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH,
    terrain_bottom_y,
)
from golf.core.rom_writer import RomWriter

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)

LO_TABLE_PRG = 0x3EFE2  # CPU $EFE2, unchanged
HI_TABLE_PRG = TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH.prg_offset
LO_READ_SITE_PRG = 0x3EE03  # SBC TerrainBottomYLo,Y - must stay vanilla
CODE_AFTER_TABLES_PRG = 0x3EFF6  # LDY #$00 / STY $27, the 16-bit shift helper


@pytest.fixture
def patched(tmp_path) -> RomWriter:
    writer = RomWriter(ROM_PATH, str(tmp_path / "wram.nes"))
    WRAM_EXPANSION_PATCH.apply(writer)
    return writer


def test_vanilla_has_expected_bytes_at_every_site(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "unused.nes"))
    for patch in TERRAIN_BOTTOM_TABLE_PATCHES:
        assert patch.can_apply(writer), patch.name


def test_vanilla_reads_zero_for_a_50_row_hole(tmp_path):
    """The bug: ScrollLimit 11 indexes past both 10-entry tables, and the
    bytes it lands on are $00/$00 - a threshold no ball Y can be below."""
    writer = RomWriter(ROM_PATH, str(tmp_path / "unused.nes"))
    assert writer.read_prg(LO_TABLE_PRG + 11, 1) == b"\x00"
    assert writer.read_prg(0x3EFEC + 11, 1) == b"\x00"


@pytest.mark.parametrize("scroll_limit", range(1, MAX_SCROLL_LIMIT + 1))
def test_every_scroll_limit_reads_its_terrain_height(patched, scroll_limit):
    """Read the two tables the way $EDFD does, straight out of the ROM."""
    low = patched.read_prg(LO_TABLE_PRG + scroll_limit, 1)[0]
    high = patched.read_prg(HI_TABLE_PRG + scroll_limit, 1)[0]
    assert high << 8 | low == terrain_bottom_y(scroll_limit)


def test_lo_read_site_is_untouched(patched):
    """Lo grew in place, so its SBC keeps pointing at $EFE2."""
    assert patched.read_prg(LO_READ_SITE_PRG, 3) == bytes([0xF9, 0xE2, 0xEF])


def test_code_after_the_grown_table_survives(patched):
    """Lo's new tail ends at $EFF2, three bytes short of this."""
    assert patched.read_prg(CODE_AFTER_TABLES_PRG, 4) == bytes([0xA0, 0x00, 0x84, 0x27])


def test_thirteen_bytes_of_the_vacated_region_remain(patched):
    """$E4F9-$E516 was 30 bytes; the Hi table takes the first 17."""
    used = len(TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH.patched)
    remaining = 0x3E517 - (HI_TABLE_PRG + used)
    assert remaining == 13


def test_round_trips_through_a_saved_rom(tmp_path):
    out = tmp_path / "wram.nes"
    writer = RomWriter(ROM_PATH, str(out))
    WRAM_EXPANSION_PATCH.apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    for patch in TERRAIN_BOTTOM_TABLE_PATCHES:
        assert patch.is_applied(reloaded), patch.name
