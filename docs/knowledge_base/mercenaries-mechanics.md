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
- **A bullet kill *can* take out more than one enemy at once** — shotgun
  spread, or a sniper/magnum round penetrating through a lined-up
  enemy, can both kill multiple targets with a single shot. This is
  rare in competitive "good" runs specifically because it hurts the
  score (a multi-kill via bullets wastes what could've been separate
  bonus kills) — players who get an accidental multi-bullet-kill will
  often just restart the run rather than keep it. So `n_bullet > 1` in
  one group is possible, just uncommon, and closer to a played-around
  outcome than a repeatable technique.
- **A real bonus+bullet mix within the same kill-group is rarer still,
  and in the author's own experience always traces back to an external
  cause** — e.g. the player weakens enemies and dashes in for a bonus
  finish, but another NPC's molotov or thrown dynamite kills one or
  more enemies (via explosion, not the player's shot) in the same
  instant. It's essentially never the *player's own* single action
  producing both kill types at once. Useful for telling a genuine mixed
  group apart from a misread: a real one usually has some other
  in-scene explanation, not just "the numbers say so."

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

## Combo counter maximum

RE5 Mercenaries has a fixed enemy pool, so the on-screen combo counter
can never exceed **150** in a single run -- there simply aren't more
enemies than that to chain a kill-streak through. Any reading above
150 is guaranteed to be a misread, not a real value, regardless of how
confident the match looked. `biomercs-ml` enforces this as
`config.MAX_PLAUSIBLE_COMBO_VALUE` (see DECISIONS.md).

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
