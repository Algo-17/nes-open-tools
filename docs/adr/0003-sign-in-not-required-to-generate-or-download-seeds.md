+++
status = "accepted"
date = 2026-09-23
area = "site"
permanent = false
revisit_when = "League rounds regularly go unrecorded because players downloaded guest ROMs, and the league wants sign-in enforced"
drafted_by = "Claude"
supersedes = []
+++

# Sign-in not required to generate or download seeds

## Context

The site records rounds through the scorecard QR code, which only works for a player
the server knows: a signed-in download gets a player ID and MAC keys, and the server
accepts rounds only for those. Round data is a large part of why the site exists, so
requiring sign-in to generate or download a seed would guarantee every ROM could
submit.

The site isn't only for one league, though, and seeds are shared in places like
Discord, where people follow a link on a phone just to see what a seed is.

## Decision

Nothing on the site requires sign-in. Signing in is encouraged, not enforced:

> I don't love the idea of users being forced to log in to either generate or download.
> I want to get round stats from people as I'm genuinely excited about gathering data
> about the holes and such, but I want it to be a carrot not a stick, basically.

Seed pages are public. Generating works signed out. Downloading signed out produces a
guest ROM, whose QR screen is disabled and whose all-zero IDs the server rejects.

## Rejected alternatives

- **Require sign-in to generate and download.** Every ROM could submit, but anyone who
  just wants to play or look at a seed is turned away.
- **Require sign-in to download only.** Guarantees submittable ROMs while keeping seeds
  public, but still turns away anyone who just wants to play a seed.
- **Require sign-in to generate only.** Deters throwaway seeds, which aren't a problem:
  people generating seeds they never play is "part of doing business".

## Consequences

- Some rounds will never be recorded, because the player downloaded a guest ROM.
- A guest ROM needs a visible marker, so a league member doesn't play a whole round
  before finding out it can't submit. Its wording and how prominent it is are still
  being decided with league members: "the point isn't to make it feel that way, just to
  make sure that league members don't play an entire round only to find out their rom
  wasn't properly logged in."
- The server has to handle signed-out users on every page, and the seed creator is
  recorded only when there is one.

## Sources

- `docs/randomizer_devplan.md`, "Users and access"; the "Polish" item for the guest
  marker
- Claude Code sessions: 2026-09-14 `e6c61dff` (the decision, the guest marker, and
  public seed pages); 2026-09-18 `f029f410` (throwaway seeds)
