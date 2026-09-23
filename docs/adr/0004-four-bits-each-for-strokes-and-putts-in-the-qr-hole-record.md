+++
status = "accepted"
date = 2026-09-23
area = "qr"
permanent = true
revisit_when = "A site seed can be built without the mercy tap-in, or the QR payload protocol changes version for another reason"
drafted_by = "Claude"
supersedes = []
+++

# Four bits each for strokes and putts in the QR hole record

## Context

The scorecard QR payload spends one byte per hole on its score: strokes and putts
packed together. Every bit is contested: the 36-byte payload has no spare bytes, only
reserved flag bits. Two splits were considered:

- **4/4:** strokes 1-16, putts 0-15.
- **5/3:** strokes 1-32, putts 0-7.

Both fields clamp rather than overflow. Clamping putts leaves the hole's score correct;
clamping strokes changes the score. On the other hand, an 8-putt hole is far more
likely than a 17-stroke one. The vanilla game counts up to 50 strokes a hole, and the
mercy tap-in patch, which caps a hole at 10, was optional when this came up.

## Decision

4/4, as used by protocol version 1.

> No, 5 bit strokes and 3 bit putts is not acceptable. The odds of someone getting an 8
> putt is way higher than someone exceeding 16 strokes. I would sooner make the mercy
> [tap-in] mandatory at 15->16 strokes than I would shorten the putt counts to 7.

It was left open as "for now". It's now effectively settled for the site: every site
seed has the mercy tap-in at 9 (`DEFAULT_MERCY_POINT` in `golf/randomizer/manifest.py`,
and `server/forms.py` keeps it off the form), so no hole on a site ROM goes past 10
strokes.

## Rejected alternatives

- **5/3** (recommended by Claude at the time). Keeps every score correct up to 32
  strokes, but clamps a 7-putt hole or worse.
- **More bits per hole.** No room: the payload has no spare bytes, and a longer URL
  means a larger QR code for the ROM to draw.

## Consequences

- Every released ROM encodes 4/4 under protocol version 1, and `/s/` URLs are baked
  into those ROMs, so the server must decode version 1 this way for as long as it
  accepts them. A different split would need a new protocol version.
- The split is not a one-line change. `payload.STROKE_BITS` sets it for the Python
  side, but the 6502 port hardcodes 4/4 in `golf/qr/port/payload.s`, where it clamps
  strokes to 1-16 and putts to 0-15 and shifts by four. `docs/scorecard_qr.md` says
  otherwise and should be corrected.
- An unplayed hole, which the game leaves as `$FF`, relies on the stroke clamp to encode
  safely as 16.
- A ROM built outside the site without the mercy tap-in (the manifest allows it) can
  still record a blow-up hole as 16.

## Sources

- `docs/scorecard_qr.md`, "Hole record" and "Open Questions"; `golf/qr/payload.py`;
  `golf/qr/port/payload.s`; `golf/randomizer/manifest.py`; `server/forms.py`
- Claude Code sessions: 2026-09-12 `e7c41e36` (the decision quoted above);
  2026-09-15 `d87d72a6` (mercy taken off the generate form and hardcoded to the
  default); 2026-09-17 `436687b3` (mercy at 9 for every site seed, noted in the step 12
  plan)
