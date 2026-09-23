+++
status = "accepted"
date = 2026-09-23
area = "patches"
permanent = false
revisit_when = "Overlap errors start firing on deliberate, identical writes often enough to be a nuisance"
drafted_by = "Claude"
supersedes = []
+++

# Any byte written by two PatchStack steps is an error

## Context

`PatchStack` builds a ROM from an ordered list of patches. Several patches write
without checking what they replace: `CoursePatch` writes course data and scorecard
totals, and the scorecard QR patch writes its image into bank 2. If two steps write the
same byte, the later one silently wins, and the ROM that comes out is wrong in a way
that may only show up in play.

When the stack was designed, the question was how strict to be about two steps writing
the same byte, in particular when both write the same value.

## Decision

Every write is attributed to the step that makes it. A step writing a byte that an
earlier step wrote is an error, even when the value is the same, and the error names
both steps and the address.

A sub-patch shared by two steps is not an overlap, because `BytePatch` writes nothing
when its bytes are already applied.

## Rejected alternatives

- **Allow a second write of the same value.** Friendlier, but two patches that happen
  to agree today can stop agreeing when one of them changes, and nothing would say they
  ever touched the same byte.
- **Last write wins.** How a wrong ROM gets built without anyone noticing.

## Consequences

- Two patches can't claim the same space without it being caught at build time. This
  surfaced the first real conflict straight away: mercy tap-in and the QR trampoline
  both at bank 13 `$BF83`, fixed by moving the trampoline to `$DCBD`.
- Deliberate rewrites have to live in a separate stack. `qr_credentials` rewrites the
  QR image's placeholder bytes and `qr_disable` rewrites its two-byte splice, so the
  finishing stage runs as its own `PatchStack` over the unfinished ROM. A test that
  builds both stages as one stack expects exactly those two overlaps and no others.
- An identical, harmless rewrite still fails the build and has to be restructured
  rather than tolerated.

## Sources

- `docs/patch_stack.md`, "Overlaps"
- Claude Code sessions: 2026-09-13 `6f3c0621` (the rule proposed, and: "For now that's
  fine, we can reevaluate later if it becomes noisy/a pain"); 2026-09-15 `fc48391f` (the
  two deliberate overlaps in the two-stage build)
