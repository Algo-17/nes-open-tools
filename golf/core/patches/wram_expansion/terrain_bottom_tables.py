"""
Expand the terrain-bottom BallY threshold tables from 10 to 17 entries, so
holes with a ScrollLimit past the vanilla range stop calling every ball
position out of bounds.

These two parallel tables, indexed by `ScrollLimit` ($010D), are read by the
ball-position probe at $EDEA - the routine the pre-swing perspective view and
the at-rest lie check both go through. Their value is the hole's terrain
height in pixels: `224 + 16 * ScrollLimit`, which is exactly
`8 * (2 * ScrollLimit + 28)` given `ScrollLimit = (terrain_height - 28) / 2`.
The probe compares the ball's 16-bit Y against it to decide whether the ball
is still on the terrain at all:

    $EDEA  LDX #$00 / STX $A0         ; tile under ball defaults to 0
    ...
    $EDFD  LDY ScrollLimit
    $EE00  LDA BallY / SEC / SBC TerrainBottomYLo,Y
    $EE06  LDA BallYHigh   / SBC TerrainBottomYHi,Y
    $EE0B  BCC $EE13                  ; on the terrain - do the real lookup
    $EE0D  JMP $EF96                  ; below it - INX x5, STX $C9 (lie 5, OOB)

Vanilla packs both tables with zero slack at $EFE2-$EFF5 in the fixed bank
(10 entries each, indices 0-9), immediately followed by real code at $EFF6.
Index 0 is a duplicate of index 1 and is never reachable (`ScrollLimit` is at
least 1 for the minimum 30-row hole); it is carried over unchanged, the same
way `ScrollThresholdLow`/`High` keeps its own dead index 0.

Found when the first live randomizer seed drew JP France hole 18 and played
it as a blank perspective scene with every shot ruled out of bounds. That
hole is 50 rows - `ScrollLimit = 11` - so both reads land past the end of
their table: the lo read takes `$EFED` and the hi read `$EFF7`, both `$00`.
A threshold of `$0000` can never be greater than `BallY`, so the `BCC` is
never taken and the probe returns lie 5 with `$A0` still 0 for *every*
position on the hole.

This is the fifth table pair this effort has had to expand, and the reason
it survived the first four rounds of tall-hole playtesting is that
`ScrollLimit = 11` is the only out-of-range index whose garbage reads
`$0000`. Every other value lands on bytes that happen to form a huge
threshold, so the guard silently never fires and the hole plays correctly:

    ScrollLimit  10     12     13     14     15     16
    threshold    $A000  $8401  $2701  $0A01  $2601  $2701

The 54-, 56-, 58- and 60-row holes that got the most attention are all in
that harmless column, and JP France 18 is the only 50-row hole in the
catalog. Expanding the tables fixes those holes too: they currently never
detect a ball below the bottom of the terrain at all, which sends a row
index past the end of `TerrainRowOffsetsLo`/`Hi` instead of ruling the ball
out of bounds.

Neither table needs new ROM space. `TerrainBottomYHi` moves into the region
the `ViewOffsetTo*` tables vacated at $E4F9 (30 bytes, see "Known Free Space"
in docs/wram_expansion.md), taking 17 and leaving 13; `TerrainBottomYLo`
then grows in place from 10 to 17 entries using the first 7 bytes `Hi` just
vacated, ending at $EFF2 with 3 bytes to spare before the code at $EFF6.
`Lo`'s read site needs no patch, since its base address never moves - same
arrangement as terrain_row_offset_tables.py and
sprite_screen_offset_tables.py.
"""

from ..byte_patch import BytePatch

#: The largest ScrollLimit a 60-row hole can have: (60 - 28) / 2.
MAX_SCROLL_LIMIT = 16


def terrain_bottom_y(scroll_limit: int) -> int:
    """The terrain's height in pixels for a hole with this `ScrollLimit`."""
    return 224 + 16 * scroll_limit


# Index 0 is unreachable dead filler duplicating index 1, as in vanilla.
_THRESHOLDS = [terrain_bottom_y(max(index, 1)) for index in range(MAX_SCROLL_LIMIT + 1)]

TERRAIN_BOTTOM_Y_LO_TABLE = bytes(value & 0xFF for value in _THRESHOLDS)
TERRAIN_BOTTOM_Y_HI_TABLE = bytes(value >> 8 for value in _THRESHOLDS)
assert len(TERRAIN_BOTTOM_Y_LO_TABLE) == len(TERRAIN_BOTTOM_Y_HI_TABLE) == 17

# The formula, checked against the 10 entries vanilla actually ships.
assert TERRAIN_BOTTOM_Y_LO_TABLE[:10] == bytes(
    [0xF0, 0xF0, 0x00, 0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70]
)
assert TERRAIN_BOTTOM_Y_HI_TABLE[:10] == bytes([0x00, 0x00] + [0x01] * 8)

# TerrainBottomYLo grows from 10 to 17 entries by claiming the first 7 bytes
# of TerrainBottomYHi's old space - indices 10-16.
TERRAIN_BOTTOM_Y_LO_GROW_PATCH = BytePatch(
    name="wram_expansion_terrain_bottom_y_lo_grow",
    description=(
        "$EFEC: grow TerrainBottomYLo from 10 to 17 entries (ScrollLimit "
        "10-16), reusing TerrainBottomYHi's vacated space"
    ),
    prg_offset=0x3EFEC,
    original=bytes([0x00, 0x00, 0x01, 0x01, 0x01, 0x01, 0x01]),
    patched=TERRAIN_BOTTOM_Y_LO_TABLE[10:],
)

# Full 17-entry TerrainBottomYHi, relocated into the space the vanilla
# ViewOffsetToAddrLow/High/AttrIndex tables vacated at $E4F9. Unlike the
# $CA40 block those bytes are not $FF filler - they are the dead original
# tables - so `original` is what is actually still sitting there.
TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH = BytePatch(
    name="wram_expansion_terrain_bottom_y_hi_free_space",
    description=(
        "New 17-entry TerrainBottomYHi table written into the space the "
        "ViewOffsetTo* tables vacated at $E4F9 (expanded from vanilla's 10 "
        "entries to support 60-row terrain)"
    ),
    prg_offset=0x3E4F9,
    original=bytes(
        [0x00, 0x00, 0x2C, 0x58, 0x84, 0xB0, 0xDC, 0x08, 0x34, 0x60]
        + [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    ),
    patched=TERRAIN_BOTTOM_Y_HI_TABLE,
)

# $EDEA ($EE08): SBC TerrainBottomYHi,Y -> the new table at $E4F9. (The
# matching TerrainBottomYLo read at $EE03 needs no change - Lo's base
# address never moves, only its length grows.)
TERRAIN_BOTTOM_Y_HI_SBC_PATCH = BytePatch(
    name="wram_expansion_terrain_bottom_y_hi_sbc",
    description="$EE08: SBC TerrainBottomYHi,Y -> SBC $E4F9,Y",
    prg_offset=0x3EE08,
    original=bytes([0xF9, 0xEC, 0xEF]),
    patched=bytes([0xF9, 0xF9, 0xE4]),
)

TERRAIN_BOTTOM_TABLE_PATCHES = [
    TERRAIN_BOTTOM_Y_LO_GROW_PATCH,
    TERRAIN_BOTTOM_Y_HI_FREE_SPACE_PATCH,
    TERRAIN_BOTTOM_Y_HI_SBC_PATCH,
]
