"""Integration tests: the relocated attribute buffer against the real vanilla ROM."""

from pathlib import Path

import pytest

from golf.core.patches import WRAM_EXPANSION_PATCH
from golf.core.patches.wram_expansion.relocate_attr_buffer import (
    ATTR_BUFFER_ADDR,
    ATTR_BUFFER_SIZE,
    RELOCATE_ATTR_BUFFER_PATCHES,
)
from golf.core.patches.wram_expansion.relocate_terrain_buffer import (
    TERRAIN_BASE_MAIN_HI_PATCH,
    TERRAIN_BASE_MAIN_LO_PATCH,
)
from golf.core.rom_writer import RomWriter

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)

FIXED_BANK_PRG = 0x3C000
FIXED_BANK_SIZE = 0x4000
# LoadTerrainAndAttrs: LDY / LDA (ptr),Y / STA buf,Y / DEY / BPL
COPY_LOOP_PRG = 0x3DB96
READ_SITES_PRG = [0x3E4A7, 0x3E4B7, 0x3E4D9, 0x3EF04]  # LDA buf,Y

LDA_ABS_Y = 0xB9
STA_ABS_Y = 0x99


def abs_y_accesses(rom: RomWriter, addr: int) -> list[int]:
    """PRG offsets of every LDA/STA abs,Y on `addr` in the fixed bank."""
    bank = rom.read_prg(FIXED_BANK_PRG, FIXED_BANK_SIZE)
    operand = addr.to_bytes(2, "little")
    return [
        FIXED_BANK_PRG + i
        for i in range(len(bank) - 2)
        if bank[i] in (LDA_ABS_Y, STA_ABS_Y) and bank[i + 1 : i + 3] == operand
    ]


@pytest.fixture
def vanilla(tmp_path) -> RomWriter:
    return RomWriter(ROM_PATH, str(tmp_path / "unused.nes"))


@pytest.fixture
def patched(tmp_path) -> RomWriter:
    writer = RomWriter(ROM_PATH, str(tmp_path / "wram.nes"))
    WRAM_EXPANSION_PATCH.apply(writer)
    return writer


def test_vanilla_has_expected_bytes_at_every_site(vanilla):
    for patch in RELOCATE_ATTR_BUFFER_PATCHES:
        assert patch.can_apply(vanilla), patch.name


def test_vanilla_touches_the_old_buffer_at_exactly_the_patched_sites(vanilla):
    """The copy's store plus the four reads - so patching those five moves
    every fixed-bank access."""
    assert abs_y_accesses(vanilla, 0x0533) == [0x3DB9A, *READ_SITES_PRG]


def test_nothing_in_the_fixed_bank_touches_the_old_buffer(patched):
    assert abs_y_accesses(patched, 0x0533) == []


def test_copy_loop_moves_90_bytes_into_wram(patched):
    # LDY #$59 / LDA ($50),Y / STA $6F9C,Y / DEY / BPL -8
    assert patched.read_prg(COPY_LOOP_PRG, 10) == bytes(
        [0xA0, 0x59, 0xB1, 0x50, 0x99, 0x9C, 0x6F, 0x88, 0x10, 0xF8]
    )


@pytest.mark.parametrize("prg_offset", READ_SITES_PRG)
def test_every_read_uses_the_new_buffer(patched, prg_offset):
    assert patched.read_prg(prg_offset, 3) == bytes([LDA_ABS_Y, 0x9C, 0x6F])


def test_buffer_ends_before_the_relocated_terrain_buffer():
    terrain_base = (
        TERRAIN_BASE_MAIN_HI_PATCH.patched[0] << 8
        | TERRAIN_BASE_MAIN_LO_PATCH.patched[0]
    )
    assert terrain_base >= ATTR_BUFFER_ADDR + ATTR_BUFFER_SIZE


def test_buffer_holds_a_60_row_hole():
    """6 attribute bytes per row, one attribute row per 4 terrain rows."""
    assert ATTR_BUFFER_SIZE == 60 // 4 * 6
