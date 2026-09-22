"""Unit tests for the green detail view shortcut patch."""

import pytest

from golf.core.patches.green_shortcut import (
    CLEAR_ONLY_SPLICES,
    ENTRY_CODE_ADDR,
    ENTRY_CODE_LIMIT,
    ENTRY_CODE_PRG_OFFSET,
    ENTRY_SPLICE_ORIGINAL,
    ENTRY_SPLICE_PRG_OFFSET,
    LIE_CALL_ORIGINAL,
    POLL_CODE_ADDR,
    POLL_CODE_LIMIT,
    POLL_CODE_PRG_OFFSET,
    POLL_SPLICE_ORIGINAL,
    POLL_SPLICE_PRG_OFFSET,
    _entry_code,
    _entry_program,
    _poll_code,
    green_shortcut_patch,
)
from tests.prg_writer import PrgImageWriter


def make_vanilla_like_rom() -> PrgImageWriter:
    """A 256KB PRG image holding the vanilla bytes at every site this patch writes."""
    rom = PrgImageWriter(bytes(16 * 0x4000))
    rom.write_prg(POLL_SPLICE_PRG_OFFSET, POLL_SPLICE_ORIGINAL)
    rom.write_prg(ENTRY_SPLICE_PRG_OFFSET, ENTRY_SPLICE_ORIGINAL)
    for _addr, prg_offset in CLEAR_ONLY_SPLICES.values():
        rom.write_prg(prg_offset, LIE_CALL_ORIGINAL)
    rom.write_prg(POLL_CODE_PRG_OFFSET, bytes([0xFF] * POLL_CODE_LIMIT))
    rom.write_prg(ENTRY_CODE_PRG_OFFSET, bytes([0xFF] * ENTRY_CODE_LIMIT))
    return rom


class TestLayout:
    def test_poll_code_fits_before_the_fast_math_tables(self):
        # $CB00 is HalfSquareTableLo; overrunning it would corrupt the tables.
        assert len(_poll_code()) <= POLL_CODE_LIMIT
        assert POLL_CODE_ADDR + POLL_CODE_LIMIT == 0xCB00

    def test_entry_code_fits_before_the_reset_stub(self):
        # $BFF3 is LD_BFF3_Mmc1ResetStub, present in every bank. With the
        # scorecard branch this is exact - there is no slack left at all.
        assert len(_entry_code()) == ENTRY_CODE_LIMIT == 52
        assert ENTRY_CODE_ADDR + ENTRY_CODE_LIMIT == 0xBFF3

    def test_splices_are_byte_neutral(self):
        patch = green_shortcut_patch()
        for sub in patch.patches:
            assert len(sub.original) == len(sub.patched), sub.name

    def test_both_splices_are_jumps_to_the_new_code(self):
        by_name = {sub.name: sub for sub in green_shortcut_patch().patches}
        poll = by_name["green_shortcut_poll_splice"].patched
        entry = by_name["green_shortcut_entry_splice"].patched
        assert poll[:3] == bytes([0x4C, POLL_CODE_ADDR & 0xFF, POLL_CODE_ADDR >> 8])
        assert entry == bytes([0x4C, ENTRY_CODE_ADDR & 0xFF, ENTRY_CODE_ADDR >> 8])


class TestPollRoutine:
    """The poll has to reproduce all three vanilla outcomes, plus the new one."""

    def test_reproduces_the_countdown_and_its_two_exits(self):
        code = _poll_code()
        # DEC $0B ... JMP $A6D0 (keep waiting), and CLC/RTS when it hits zero.
        assert bytes([0xC6, 0x0B]) in code
        assert bytes([0x4C, 0xD0, 0xA6]) in code
        assert bytes([0x18, 0x60]) in code

    def test_keeps_the_a_button_abort(self):
        # SEC/RTS is what $A6E9 did, and what the A button must still reach.
        assert bytes([0x38, 0x60]) in _poll_code()

    def test_masks_every_button_before_distinguishing_them(self):
        # AND #$B0 (A|Select|Start) first, so a quiet frame costs one compare.
        code = _poll_code()
        assert code[:2] == bytes([0x29, 0xB0])
        assert bytes([0x29, 0x30]) in code

    def test_shortcut_buttons_are_tested_before_a(self):
        """Order matters: `AND #$30` leaves Z set for an A-only press.

        Testing A first would work too, but testing the masked value for A
        after masking for Select/Start would not - so the routine has to
        isolate the shortcut bits and branch away before touching A.
        """
        code = _poll_code()
        assert code.index(bytes([0x29, 0x30])) < code.index(bytes([0x8D, 0xBB, 0x05]))

    def test_the_flag_records_which_button_was_pressed(self):
        """`STA` stores the isolated bit, so $20 means Select and $10 Start.

        That is why adding Start cost the poll nothing: the mask widened and
        the existing store carries the distinction for free.
        """
        code = _poll_code()
        mask = code.index(bytes([0x29, 0x30]))
        store = code.index(bytes([0x8D, 0xBB, 0x05]))
        # nothing between the mask and the store can disturb A
        assert code[mask + 2 : store] == bytes([0xF0, 0x03])

    def test_flags_the_shortcut_with_the_select_bit_itself(self):
        # STA $05BB with A still holding $20 - no LDA #$01 needed, and any
        # nonzero value satisfies the wrapper's BEQ.
        assert bytes([0x8D, 0xBB, 0x05]) in _poll_code()

    def test_a_set_flag_cuts_every_later_step_short(self):
        """$A695 is the only call site that acts on the carry.

        The four open steps ($A641/$A646/$A64B/$A650), the four close steps
        and the out-of-bounds blink at $A66F all discard it, so without this
        a Select caught during the open animation would set the flag and then
        sit through the remaining ~98 frames before anything read it.
        """
        code = _poll_code()
        load_flag = code.index(bytes([0xAD, 0xBB, 0x05]), 13)
        # LDA $05BB / BNE, reached on the no-button path, before DEC $0B
        assert code[load_flag + 3] == 0xD0
        assert load_flag < code.index(bytes([0xC6, 0x0B]))

    def test_the_set_flag_check_branches_to_the_shared_abort(self):
        code = _poll_code()
        abort = code.index(bytes([0x38, 0x60]))
        branch = code.index(bytes([0xAD, 0xBB, 0x05]), 13) + 3
        # BNE operand is signed; resolve it the way the CPU would
        offset = code[branch + 1] - 256
        assert branch + 2 + offset == abort


class TestEntryRoutine:
    def test_reaches_the_panel_only_through_the_flag_clear(self):
        """Both routes into the lie panel must zero the flag first.

        The menu reaches ShowBallLiePopup at $9785 and ignores the flag, so
        without this a Select pressed there would survive to fast-forward a
        later panel.
        """
        program = _entry_program()
        code = program.code
        clear = program.at("ClearFlagThenLie")
        # the clear tail-calls the panel; nothing else in the routine does
        assert code[clear:] == bytes([0xA9, 0x00, 0x8D, 0xBB, 0x05, 0x4C, 0xDE, 0xA5])
        assert code.count(bytes([0x4C, 0xDE, 0xA5])) == 1
        assert bytes([0x20, 0xDE, 0xA5]) not in code

    def test_entry_calls_the_flag_clear_first(self):
        program = _entry_program()
        target = program.symbol("ClearFlagThenLie")
        assert program.code[:3] == bytes([0x20, target & 0xFF, target >> 8])

    def test_unset_flag_rejoins_the_vanilla_path(self):
        # $87F2 is the instruction the displaced JSR used to fall through to.
        assert bytes([0x4C, 0xF2, 0x87]) in _entry_code()

    def test_select_and_start_reach_different_screens(self):
        """$20 falls through to the green; anything else takes the scorecard."""
        code = _entry_code()
        cmp_select = code.index(bytes([0xC9, 0x20]))
        assert code[cmp_select + 2] == 0xD0  # BNE Scorecard
        # ExecuteFarCall with in-game menu item 0's own inline arguments
        assert bytes([0x20, 0x72, 0xD3, 0x02, 0x76, 0xAE]) in code

    def test_both_screens_share_the_fade_in_and_the_wait(self):
        program = _entry_program()
        code = program.code
        after_draw = program.at("AfterDraw")
        assert code[after_draw : after_draw + 3] == bytes([0x20, 0x23, 0xD8])
        # the scorecard branch rejoins there rather than repeating it
        assert bytes([0x4C, program.symbol("AfterDraw") & 0xFF, 0xBF]) in code

    def test_set_flag_draws_the_green_between_fades(self):
        code = _entry_code()
        fade_out = code.index(bytes([0x20, 0x3C, 0xD8]))
        green = code.index(bytes([0x20, 0xA9, 0x95]))
        fade_in = code.index(bytes([0x20, 0x23, 0xD8]))
        assert fade_out < green < fade_in

    def test_waits_for_an_input_event_before_leaving_the_green(self):
        # JSR $D188 / BEQ back to itself.
        assert bytes([0x20, 0x88, 0xD1, 0xF0, 0xFB]) in _entry_code()

    def test_exits_through_the_vanilla_course_view_restore(self):
        # $87E3 already fades out, redraws the course view, fades in and
        # jumps to $87F2 - so the patch reuses it rather than repeating it.
        assert bytes([0x4C, 0xE3, 0x87]) in _entry_code()


class TestApplication:
    def test_applies_to_a_vanilla_like_rom(self):
        rom = make_vanilla_like_rom()
        patch = green_shortcut_patch()
        assert patch.can_apply(rom)
        patch.apply(rom)
        assert patch.is_applied(rom)

    def test_refuses_a_rom_whose_free_space_is_taken(self):
        rom = make_vanilla_like_rom()
        rom.write_prg(POLL_CODE_PRG_OFFSET, bytes([0x60]))
        assert not green_shortcut_patch().can_apply(rom)

    def test_refuses_a_rom_whose_splice_site_differs(self):
        rom = make_vanilla_like_rom()
        rom.write_prg(POLL_SPLICE_PRG_OFFSET, bytes([0xEA]))
        assert not green_shortcut_patch().can_apply(rom)

    def test_is_not_applied_on_a_vanilla_rom(self):
        assert not green_shortcut_patch().is_applied(make_vanilla_like_rom())

    def test_is_registered(self):
        from golf.core.patches.registry import PATCH_SPECS

        assert "green_shortcut" in PATCH_SPECS


class TestSplicedOriginals:
    """The `original` bytes are what the vanilla ROM must hold at each site."""

    def test_poll_splice_replaces_the_a_button_test(self):
        # AND #$80 / BNE $A6E9
        assert bytes([0x29, 0x80, 0xD0, 0x06]) == POLL_SPLICE_ORIGINAL

    def test_entry_splice_replaces_the_lie_popup_call(self):
        # JSR $A5DE
        assert bytes([0x20, 0xDE, 0xA5]) == ENTRY_SPLICE_ORIGINAL

    def test_clear_only_splices_replace_the_same_call(self):
        # JSR $A5DE at the post-shot, water-penalty and menu call sites
        assert bytes([0x20, 0xDE, 0xA5]) == LIE_CALL_ORIGINAL
        assert set(CLEAR_ONLY_SPLICES) == {"shot_result", "water_penalty", "menu"}

    def test_clear_only_splices_target_the_flag_clear(self):
        by_name = {sub.name: sub for sub in green_shortcut_patch().patches}
        target = _entry_program().symbol("ClearFlagThenLie")
        expected = bytes([0x20, target & 0xFF, target >> 8])
        for site in CLEAR_ONLY_SPLICES:
            assert by_name[f"green_shortcut_clear_{site}"].patched == expected


class TestOversizeGuards:
    def test_poll_overflow_is_reported(self, monkeypatch):
        monkeypatch.setattr("golf.core.patches.green_shortcut.POLL_CODE_LIMIT", 4)
        with pytest.raises(ValueError, match="LiePopupPoll is"):
            _poll_code()

    def test_entry_overflow_is_reported(self, monkeypatch):
        monkeypatch.setattr("golf.core.patches.green_shortcut.ENTRY_CODE_LIMIT", 4)
        with pytest.raises(ValueError, match="GreenShortcutEntry is"):
            _entry_code()
