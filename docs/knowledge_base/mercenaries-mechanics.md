# Resident Evil 5/6 "The Mercenaries" — mechanics

Ground truth from the author's own competitive experience. See
[README.md](./README.md) for how to use this file.

## Scoring: the clock is the real resource

The main scoring loop isn't "kill everyone before time runs out" — it's
"kill everyone in a way that keeps paying time back into the clock,"
because whatever time is left when the last enemy (of the fixed pool,
e.g. 150) dies converts directly into score at the end (roughly 1000
points per second remaining). A kill that doesn't extend the clock is
strictly worse than a slower kill that does, if the extension outweighs
the time spent setting it up.

### Bonus kills vs. bullet kills

- A kill via a melee/dash finisher grants **+5 seconds** to the clock —
  a "bonus kill".
- A kill via gunfire alone grants no time — a "**bullet kill**" (the
  community's own term for this).
- When multiple enemies die in the same instant, the on-screen "+5"
  popup renders only **once** no matter how many of them were bonus
  kills, but the clock still increases by +5s per bonus kill in that
  group (e.g. 3 simultaneous bonus kills → clock +15s, one popup shown).
  This is why HUD-popup text is not a reliable signal for counting bonus
  kills — the run timer's actual value is.

## Character techniques

### Wesker (STARS) — the meta character for raw score

Wesker's special ability is a **dash** (not a teleport). Signature loop:
2 shots from the Samurai Edge (~350 damage each, more with body-shot
multipliers) to bring an enemy (~800 HP for common enemies) down to a
sliver of health, then a dash through them — the dash itself deals a
small amount of extra damage (~100) and staggers, enough to finish the
enemy via the dash, which counts as a melee-category kill and triggers
the +5s bonus. Chained across a room, this looks like one continuous
motion rather than discrete shoot-shoot-kill cycles. This is considered
the dominant character for maximizing score, because the loop is highly
repeatable/drillable once practiced — the skill ceiling is mostly
execution speed and consistency.

### Chris (STARS) — no special ability, much harder to master

Chris has no special ability (no dash, no equivalent tool). His main
scoring technique: 3 shots (2 body, 1 leg) can stun an enemy into a
specific position, followed by an **uppercut** to kill. The technical
difficulty is in multi-kills: to uppercut multiple enemies together, you
first have to actively group/herd them into position, damage them enough,
and land the uppercut while they're clustered — much harder in practice
than in description. Enemies don't always stun (see below), so
improvisation is constantly required.

Chris's skill ceiling is fundamentally different from Wesker's: it's not
a repeatable execution string, it's real-time decision-making under
uncertainty. The actual skill is contingency handling — always having a
next enemy to redirect a stun attempt toward, so one failed stun doesn't
collapse the whole planned cluster — rather than getting reliably lucky
with stuns.

**Stun randomness:** most enemies have a randomized chance to stun on the
right hit; a few specific enemies/moments guarantee it. The randomness is
real but smaller than it first appears — good positioning and always
having a backup enemy to work with reduces its practical impact a lot.
It's a variance-management skill, closer to poker than to a rhythm game:
top players aren't the ones who get luckier stuns, they're the ones whose
runs degrade the least when a stun fails.

## Legal combination rules (platform/game/mode/character/stage)

Not every character, stage, or mode is legal in every
platform/game/mini-game combination — this is real competitive-rules
complexity, not incidental. Concrete example: the RE6 × Left 4 Dead 2
crossover DLC added four characters (Coach, Ellis, Nick, Rochelle) that
are legal **only** on PC, and **only** in No Mercy mode — not on other
platforms, and not in other modes even on PC. This is the kind of
combination that a legality/rules model needs to represent as the
intersection of platform *and* mode *and* character, not any one of those
alone.

(This specific rules-modeling problem is really about the separate
`biomercs`/`biomercs-api` leaderboard project's database schema, not
`biomercs-ml` — noted here because the example is genuinely useful domain
knowledge that could matter again.)
