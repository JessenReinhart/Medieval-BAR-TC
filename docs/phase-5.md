# Phase 5: Victory Conditions, Medieval HUD & Tactical Depth

> **Status: IMPLEMENTED & PROBE-VERIFIED.** Slices 1–6 are complete, unit-tested (1114 tests pass,
> 77 Lua files clean), and the Slice 6 end-to-end headless probe passed all six verdicts at
> f=40/100/160/260/300/300 (`settlement-start`, `economy-flow`, `military-engagement`, `tc-destroyed`,
> `victory-gameover winner=1 reason=tc_destruction`, `probe-complete`). **Recorded implementation
> deviations:** (a) Slice 4 TC garrison cap = 10 (spec below said 8); no `tower_arrow` weapondef
> was added. (b) Slice 2 `popLine` → `"Pop: 12/40"` (colon) per task spec, not the colon-less form
> in the Slice 2 section below. See `docs/handoff.md` for load-bearing cross-slice details.

Phase 5 closes the gameplay loop. Phases 1–4 delivered combat, economy, logistics, siege,
production chains, veteran tiers, hauling, and a basic skirmish AI — all systems that generate
and consume resources but do not yet decide *who wins*. Phase 5 adds the win/loss layer, a
readable medieval status HUD, market depth, garrisonable defenses, tactical charge/flank/brace
dynamics, and a single end-to-end automated match probe that runs from settlement start to a
`GameOver` verdict.

All art reuses CC-BY-SA 3.0 0 A.D. static assets via `tools/assets/convert_0ad.py`. No restricted
BAR CC-BY-NC-ND assets are used anywhere; the HUD renders with the engine's built-in font and
primitives only. Code is GPL-v2 (see `LICENSE.md` and `licenses/0ad-art.txt`).

## Architectural goals

1. **Policy is pure, side effects are synced.** Every decision table (victory conditions,
   exchange rates, garrison caps, charge/bracing math) lives in a
   `scripts/medieval_*.lua` module loadable by bare Lua 5.1/LuaJIT with no `VFS`/`Spring`. The
   paired `luarules/gadgets/gadget_medieval_*.lua` owns the `GG.*` export surface, all
   `Spring.*` calls, and event callins.
2. **One authoritative damage pipeline.** Supply (Phase 3), garrison (Slice 4), and tactics
   (Slice 5) all scale outgoing damage. They must not double-apply. Slice 5 owns the single
   `UnitPreDamaged` hook and composes a deterministic multiplier chain, not independent hooks.
3. **UI is a dumb renderer.** The Slice 2 HUD widget draws nothing but rules params that synced
   gadgets publish. It never touches `GG.MedievalEconomy` (synced-only) directly.
4. **Determinism and PASS/FAIL.** Every slice ships a headless probe gadget gated on a modoption,
   a startscript, and a runner that greps for `*-verdict PASS` lines. Victory itself is the
   Slice 6 end-to-end probe's terminal verdict.
5. **Engine-faithful mechanics.** Prefer engine primitives (transport-capacity garrisoning,
   `Spring.GameOver`) over bespoke reimplementation, and document every place the engine lacks a
   native lever (dynamic per-shot projectile count is the known one — see Slice 4).

## Modoptions added by Phase 5 (extend `modoptions.lua`)

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `victorymode` | list | `tc_destruction` | `conquest` / `tc_destruction` / `regicide` / `surrender` |
| `medievalvictory` | bool | false | Gate the Slice 1/6 victory probe gadget |
| `medievalhud` | bool | true | Gate the Slice 2 HUD widget |
| `medievalmarket` | bool | false | Gate the Slice 3 market probe |
| `medievalgarrison` | bool | false | Gate the Slice 4 garrison probe |
| `medievaltactics` | bool | false | Gate the Slice 5 tactics probe |

`deathmode` already exists with the single `neverend` item. Phase 5 keeps `neverend` as the item
list entry but the victory gadget now *replaces* the engine's death logic as the authoritative
`GameOver` trigger; the existing `neverend` value simply means "no engine auto-end, gadget decides".

---

## Slices

### Slice 1 — Match Objectives & Victory/Defeat Engine (COMPLETE)

Configure and evaluate win/loss per ally team; on a terminal condition, declare winners through
`Spring.GameOver`.

**Pure module `scripts/medieval_victory.lua`** (no engine calls):
- Constants: `WIN_MODES = { "conquest", "tc_destruction", "regicide", "surrender" }`,
  `DEFAULT_MODE = "tc_destruction"`, `SURRENDER_MIN_FRAMES = 120`, `REGICIDE_KING_DEF = "medieval_king"`.
- Classification `classifyDef(defName)` → `"town_center"`, `"king"`, `"military"`, `"civilian"`,
  `"building"`, `"other"`. Unit names source-of-truth: `medieval_town_center`, `medieval_king`
  (new, Slice 1), the military roster from `scripts/medieval_recruitment.lua` `UPKEEP` keys, and
  `medieval_villager`/`medieval_cart`.
- `evaluate(state)` → `{ winnerAllyTeam = <id|nil>, losers = {allyTeam,…}, reason = <string|nil> }`.
  `state` is a pure projection `{ [allyTeamID] = { tcs, kings, units, surrendered } }` assembled by
  the gadget so the policy stays unit-testable.
  - `conquest`: a team loses when `tcs == 0 and units == 0`.
  - `tc_destruction`: a team loses when `tcs == 0` (units may survive but the settlement is gone).
  - `regicide`: a team loses when `kings == 0`; economy and remaining units are irrelevant.
  - `surrender`: a team loses when `surrendered == true`; a match ends immediately if all but one
    ally team are eliminated.
  - Totality: missing/malformed `state` returns `{ winnerAllyTeam = nil, reason = nil }` (no crash).
- Helpers: `teamEliminated(state, allyTeam, mode)`, `remainingAllyTeams(state)`,
  `canSurrender(state, allyTeam, frame)` (frame-floor gate under `SURRENDER_MIN_FRAMES`).

**Synced gadget `luarules/gadgets/gadget_medieval_victory.lua`**:
- `layer = 6` (after economy/housing/gather/recruitment/skirmish AI, which run at layers 1–5).
  Gated on modoption `medievalvictory=1` for probe runs; otherwise reads `victorymode` and runs in
  "live" mode with a conservative 15-frame cadence.
- Tracks live per-ally-team counts via `Initialize`, `UnitCreated`, `UnitDestroyed`, `UnitTaken`,
  `UnitGiven`, `TeamDied`; classifies by `VFS.Include("scripts/medieval_victory.lua")`.
- Regicide mode: the first spawned (or first `medieval_king`) is registered; teams with no king at
  start get one via `Spring.CreateUnit("medieval_king", …)` at their start position.
- Surrender mode: exposes `GG.MedievalVictory.SurrenderTeam(teamID)`; also accepts an unsynced
  `/surrender` chat command through `RecvLuaMsg` (validated: only for the caller's team, and only
  under `surrender` mode).
- On `evaluate` returning a winner: records `GG.MedievalVictory.status = { winner, reason }`,
  publishes `victory_winner`, `victory_reason` game-rules params, then calls
  `Spring.GameOver({ [winnerAllyTeam] = 1 })` (or the engine's winner-tuple form — **verify the
  exact signature against Recoil 2026.07.04 in the Slice 1 probe**; `luarules/gadgets.lua` already
  dispatches `GameOver(winningAllyTeams)` as a callin, so the engine end-of-game path exists).
- `GG.MedievalVictory` API: `GetMode`, `GetStatus`, `Evaluate`, `SurrenderTeam`, `RegisterKing`,
  `ForceDefeat(teamID)`.
- Observes `gadget:GameOver(winningAllyTeams)` purely to log the terminal verdict for the probe;
  it never re-triggers.

**Probe stages** (`gadget_phase5_slice1_victory_probe.lua`, `startscript_slice1.txt`):
1. f=20 spawn two ally teams each with one TC and one king.
2. f=40 assert `conquest` no-elimination (both alive).
3. f=60 destroy team 0's TC and units; assert `-verdict PASS` (team 0 eliminated under `tc_destruction`).
4. f=90 respawn, kill only team 0's king under `regicide`; assert `-verdict PASS`.
5. f=120 call `GG.MedievalVictory.SurrenderTeam(0)`; assert `surrender-verdict PASS` and
   `victory-gameover PASS` (winner team 1, reason logged).

**Test plan** (`tests/test_phase5_slice1.py`): purity (no `VFS`/`Spring`), classification table,
all four `evaluate` modes, totality fallbacks, `canSurrender` frame-floor, `GameOver` winner-tuple
shape, and the gadget contract export names.

---

### Slice 2 — Medieval Economy HUD & Status Bar (COMPLETE)

A LuaUI widget rendering the four-résource stockpiles, population, starvation alert, and idle
villager count — all from synced rules params.

**Synced publisher `luarules/gadgets/gadget_medieval_hud.lua`** (layer 2, always-on):
- The economy gadget already publishes `team_<id>_food/wood/stone/iron`. This tiny gadget adds the
  HUD-only aggregates so no widget reads synced `GG` tables:
  `team_<id>_pop`, `team_<id>_popcap`, `team_<id>_idle_villagers`, `team_<id>_starvation`
  (0/1), `victory_winner`, `victory_reason` passthrough.
- Sources: `GG.MedievalHousing` for pop/cap, `GG.MedievalGather` assignment counts for idle
  villagers, `GG.MedievalVictory` for terminal state. Recached on a 30-frame cadence.

**Pure formatter `scripts/medieval_hud.lua`** (no engine calls; keeps the widget testable):
- `formatStock(n)` → `"1.2k"` style; `stockLine(resources)` → the 4-cell text layout;
  `starvationAlert(food, upkeepPerTick)` → `{ level = "ok"|"low"|"critical", text }`;
  `popLine(pop, cap)` → `"Pop 12/40"`; `idleLine(n)` → `"Idle: 3"`.

**Widget `LuaUI/Widgets/gui_medieval_hud.lua`**:
- `widget:GetInfo()` metadata; gated on `medievalhud == true` (and skips spectating-owned teams).
- Reads rules params via `Spring.GetTeamRulesParam(teamID, key)` in `widget:DrawScreen`.
- Top-left panel: engine font, `gl.Color` + `gl.Text`; food/wood/stone/iron stockpiles, pop/cap,
  idle villagers. Starvation cell flashes red (blink based on `Spring.GetTimer` phase, no art).
  Victory/defeat overlay (`victory_winner`/`victory_reason`) drawn centered when set.
- No new art: text + colored rects only. Shared formatter logic is `VFS.Include`d from
  `scripts/medieval_hud.lua` so the widget and tests agree byte-for-byte.

**Probe** (`gadget_phase5_slice2_hud_probe.lua`): not a synced sim probe — the widget renders
unsynced. Verification is twofold: (a) `tests/test_phase5_slice2.py` exercises the pure formatter
and asserts the rules-param keys exist in the publisher source; (b) a manual/CI smoke check that
`gui_medieval_hud.lua` loads under LuaUI with `medievalhud=1`. Note the headless engine has no
LuaUI draw surface, so no `*-verdict PASS` from the widget itself; the publisher probe asserts the
params are emitted (`hud-params-verdict PASS`) inside the Slice 3/4 shared probe run.

**Test plan** (`tests/test_phase5_slice2.py`): formatter purity + gold values, param-key contract
(regex over `gadget_medieval_hud.lua`), starvation threshold boundaries.

---

### Slice 3 — Market & Trade Exchange (COMPLETE)

A `medieval_market` building enabling resource-to-resource barter with supply/demand-weighted
rates, plus cart-driven trade routes between markets that mint a surplus bonus for the owner.

**Building `units/medieval_market.lua`**:
- `medieval_market` — static, no fight, cost wood 80 / stone 40, `customparams =
  { resource_cost_wood = 80, resource_cost_stone = 40, market = true, armor_class = "building" }`.
- Art: reuse an existing converted 0 A.D. civic mesh via `tools/assets/convert_0ad.py`; if no
  distinct market mesh is already available, **fall back to the existing
  `medieval_granary`/wall model** rather than introduce new CC-BY-NC-ND art. Provenance recorded in
  `tools/assets/0ad-manifest.json` exactly as Phase 4 did.

**Pure module `scripts/medieval_market.lua`** (no engine calls):
- `BASE_RATES = { food = 1.0, wood = 1.0, stone = 1.5, iron = 2.0 }` (stone/iron are scarcer),
  `ELASTICITY = 0.5`, `TRADE_MARGIN = 0.1`, `TRADE_SURPLUS = { food=3, wood=3, stone=2, iron=1 }`,
  `ROUTE_RADIUS = 400`.
- Rate model: `exchangeRate(state, from, to)` = `base[to]/base[from]` scaled by supply/demand
  elasticity `(1 + ELASTICITY * (stock[from] - stock[to]) / SCALE)`. Deterministic and injectable
  via the `state` projection.
- `tradeQuote(state, from, to, amount)` → `{ cost, ok }`; `canTrade`, `applyTrade` (mutates the
  caller's stockpile copy — pure, the gadget commits via `GG.MedievalEconomy.Transact`).
- `routeValue(state, fromPos, toPos)` → proportion of `TRADE_MARGIN` earned scaling with distance,
  `selectRouteDestination(marketPositions)` (nearest unpaired market within `ROUTE_RADIUS`).
- **No new "gold" resource.** Barter runs on the existing Food/Wood/Stone/Iron four-résource pool;
  gold is explicitly out of scope (avoids migrating Phase 2's discrete economy core).

**Synced gadget `luarules/gadgets/gadget_medieval_market.lua`** (layer 4, `medievalmarket=1` probe
gate; live mode reads `victorymode`-adjacent economy cadence):
- Tracks market buildings per team; `GG.MedievalMarket = { GetRates, Trade, RegisterRoute,
  GetRoutes, CreateRoute }`.
- `Trade(teamID, from, to, amount)` commits atomically through `GG.MedievalEconomy.Transact`
  (withdraw cost, deposit gain, respecting `MAX_STOCKPILE`).
- Routes: a `medieval_cart` assigned to a market pair performs a Phase 4 haul; on completion the
  owner receives `TRADE_SURPLUS` of a rotating resource (deterministic round-robin per route).
  Reuses `GG.MedievalLogistics` road graph and `GG.MedievalHauling` rather than a new pathing layer.

**Probe** (`gadget_phase5_slice3_market_probe.lua`):
1. f=20 place two markets (team 0) + supply stock.
2. f=40 assert `rate-verdict PASS` (gold-value rate for food→iron matches the pure function).
3. f=60 execute one barter trade; assert `trade-verdict PASS` (stock delta exact).
4. f=90 place second market + cart, register route, complete one haul; assert `route-verdict PASS`.

**Test plan** (`tests/test_phase5_slice3.py`): rate elasticity math, quote/apply invariants
(no free money, stock non-negative), route distance scaling, surplus round-robin, purity, and
gadget contract exports.

---

### Slice 4 — Garrisoning & Town Defense (COMPLETE)

Villagers and archers shelter in Town Centers and Towers; shelter grants damage immunity and slow
heal, and each garrisoned archer scales the structure's defensive output. Uses the engine's
transport-capacity primitive for safe, deterministic shelter.

**Pure module `scripts/medieval_garrison.lua`** (no engine calls):
- `GARRISON_CAP = { medieval_town_center = 8, medieval_tower = 4 }`,
  `ARCHER_DAMAGE_PER = 0.15` (per garrisoned ranged unit, additive), `SHELTER_HEAL_PER_TICK = 1`,
  `HEAL_TICK_FRAMES = 30`, `GARRISONABLE = { medieval_villager = true, medieval_archer = true,
  medieval_crossbow = true }`.
- `canGarrison(buildingDef, count)` (cap check), `garrisonAllowed(unitDef)` (ranged/civilian only),
  `garrisonDamageMult(garrisonCount)` = `1 + min(count, cap) * ARCHER_DAMAGE_PER`,
  `shelterHealFor(frameDelta)`.

**Units/buildings**: add transport fields to `medieval_town_center` and `medieval_tower`:
`isTransport = true`, `transportCapacity` (8 / 4), `transportSize = 1`, `transportMass = 50`,
`canLoad = true`, `canUnload = true`. Tower gains defensive weapon `tower_arrow` in
`gamedata/weapondefs.lua` (ranged class, modest damage, no move) so garrisoned towers can reply to
attackers; the TC remains unarmed (shelter only) to preserve its role as an economy/reinforce hub.

**Synced gadget `luarules/gadgets/gadget_medieval_garrison.lua`** (layer 4, `medievalgarrison=1`
probe gate):
- Tracks shelter occupancy via `UnitLoaded`/`UnitUnloaded`/`UnitDestroyed`;
  `GG.MedievalGarrison = { Occupy, Eject, GetOccupancy, GetDamageMult }`.
- Shelter immunity + heal are engine-provided (transport load removes the unit from the map). The
  gadget adds `SetUnitHealth` recovery on a 30-frame tick for loaded units.
- Publish `team_<id>_garrison_bonus` (total garrison damage scaling) and per-unit
  `garrison_count` rules params. Outgoing damage scaling is applied via `UnitPreDamaged`: a
  garrisoned tower's damage is multiplied by `garrisonDamageMult`.

> **Engine limitation (documented, not worked around):** Spring weapondefs have no per-volley
> dynamic projectile-count lever. "Boosts projectile count" is realized as a deterministic
> damage multiplier per garrisoned archer (consistent with the Phase 3 supply-bonus precedent),
> not by spawning extra projectiles. The three-shot `burst` on `tower_arrow` is a fixed cosmetic
> volley. This is stated here so Slice 5's damage pipeline composes with it cleanly.

**Probe** (`gadget_phase5_slice4_garrison_probe.lua`):
1. f=20 place a town center + 5 villagers + 3 archers; issue `CMD.LOAD_UNITS`.
2. f=40 assert `shelter-verdict PASS` (5 loaded, cap 8 respected).
3. f=60 assert `damage-mult-verdict PASS` (tower mult = `1 + 3*0.15 = 1.45`).
4. f=90 assert `heal-verdict PASS` (loaded unit HP rose over one tick).
5. f=120 eject all; assert `eject-verdict PASS` (occupancy 0, units restored).

**Test plan** (`tests/test_phase5_slice4.py`): cap math, `garrisonAllowed` gate, damage-mult
graph, heal tick math, purity, gadget contract, and a source check that TC/tower defs carry the
transport fields.

---

### Slice 5 — Tactical Combat Dynamics (COMPLETE)

Cavalry shock-charge bonuses, spearman brace-vs-charge counter, directional flank damage, and a
switchable defensive stance. Consolidates all outgoing-damage scaling into one deterministic hook.

**Pure module `scripts/medieval_tactics.lua`** (no engine calls):
- Constants: `CHARGE_SPEED_THRESHOLD`, `CHARGE_DMG_MULT_MAX = 1.6`, `BRACE_DMG_REDUCTION = 0.5`,
  `BRACE_BONUS_VS_CAVALRY = 1.25`, `FLANK_SIDE_MULT = 1.15`, `FLANK_REAR_MULT = 1.25`,
  `STANCE_DEF_ARMOR_MULT = 1.25`, `STANCE_DEF_DAMAGE_MULT = 0.8`,
  `STANCES = { "standard", "defensive" }`.
- `chargeMult(curSpeed, distMoved)` → ramps from 1.0 to `CHARGE_DMG_MULT_MAX` on sustained approach.
- `braceMult(isSpearman, attackerIsCavalry, isBracing)` → spearmen bracing a frontal charge negate
  the charge bonus and gain `BRACE_BONUS_VS_CAVALRY`; non-cavalry attackers are unaffected.
- `flankMult(attackerHeading, defenderHeading)` → rear > side > front.
- `stanceArmorMult(stance)`, `stanceDamageMult(stance)`, `compose(...)` — the single ordered
  multiplier chain `supply * garrison * charge * brace * flank * stance` (order is fixed and
  tested so Phase 3 supply and Slice 4 garrison never double-apply).

**Units**: add `medieval_spearman` (reuses an existing converted infantry mesh — no new art) with
`spear` weapon (`gamedata/weapondefs.lua`: melee, anti-cavalry, `customparams.damage_class="melee"`,
plus `counter_cavalry=true`). Add to `scripts/medieval_recruitment.lua` (`COSTS`, `UPKEEP`, gear
unneeded), `scripts/medieval_housing.lua` (`unitConsumesPop` = 1), and the Slice-1 victory
classification (military). `medieval_cavalry`/`medieval_knight` gain `charge=true`; the lance
weapon is already melee-ranged.

**Synced gadget `luarules/gadgets/gadget_medieval_tactics.lua`** (layer 5, `medievaltactics=1`
probe gate):
- Tracks per-unit velocity/heading deltas between `GameFrame` ticks to estimate charge distance;
  tracks stance state (default `standard`; toggled via `/stance defensive` unsynced command and
  `RecvLuaMsg`, or `GG.MedievalTactics.SetStance`).
- Owns the sole `UnitPreDamaged` hook: calls `scripts/medieval_tactics.lua` compose with the
  current supply/garrison multipliers read from rules params, then scales insult received by the
  defender (`UnitPreDamaged` receives attacker/defender IDs and heading via `Spring.GetUnitHeading`).
  Applies defensive-stance armor as a damage reduction instead of a raw HP change.
- `GG.MedievalTactics = { SetStance, GetStance, GetChargeState, Compose }`.

**Probe** (`gadget_phase5_slice5_tactics_probe.lua`):
1. f=20 spawn a cavalry + spearman + target infantry, assign headings.
2. f=40 assert `charge-verdict PASS` (cavalry charge mult ≥ threshold after approach).
3. f=60 spear braces vs charging cavalry; assert `brace-verdict PASS` (charge negated, counter bonus).
4. f=90 assert `flank-verdict PASS` (rear hit mult = 1.25).
5. f=120 set defensive stance; assert `stance-verdict PASS` (armor mult applied, damage reduced).

**Test plan** (`tests/test_phase5_slice5.py`): compulsory chain order/commutativity (supply,
garrison, charge, brace, flank, stance), charge ramp boundaries, brace vs non-cavalry and
wrong-facing cases, flank quadrant math, stance toggles, purity, and gadget contract.

---

### Slice 6 — Full Skirmish Match Integration & Victory Probe (COMPLETE)

The end-to-end automated match: two teams start with a settlement, the Slice 6 skirmish AI plays,
and a `tc_destruction` (or `conquest`) win is reached, firing `Spring.GameOver`.

**Probe gadget `luarules/gadgets/gadget_phase5_slice6_integration_probe.lua`** (layer 10):
- Gated on `medievalvictory=1` + `skirmishai=1`. Spawns two settlements (TC + villagers + houses +
  resources) at fixed start positions `(1800, 2400)` and `(4200, 2400)`; team 1 runs
  `GG.MedievalSkirmishAI` with `victorymode=tc_destruction`.
- Verdicts, all frame-bounded:
  1. `settlement-start PASS` — both teams have TCs, villagers, and starting stockpiles.
  2. `economy-flow PASS` — team 0 stockpiles change across the match (no deadlock).
  3. `military-engagement PASS` — team 1 field army engages team 0 (fire/damage events observed).
  4. `tc-destroyed PASS` — team 0's TC reaches 0 HP (siege/melee path works under victory watch).
  5. `victory-gameover PASS` — `victory_winner == 1` and `victory_reason == "tc_destruction"`
     observed through `Spring.GameOver`, matching `GG.MedievalVictory.GetStatus()`.
- The probe records `f_gameover` (frame at which `GameOver` fired) and asserts it is finite and
  within budget.

**Runner** `tools/launch/run_phase5_slice6_probe.py` + `tools/launch/startscript_slice6b.txt`:
- Mirrors `run_phase2_slice6_probe.py`; launches against `startscript_slice6b.txt` with
  `medievalvictory=1`, `skirmishai=1`, `victorymode=tc_destruction`, `debugcommands=1:forcestart`.
  Budget ~120 s wall clock (the headless sim runs 16–28 f/s; the full match, including a
  `medieval_catapult` `reloadtime = 5.0`, needs the enlarged frame window).

**Test plan** (`tests/test_phase5_slice6.py`): pure win-projection integration
(`evaluate` fed by a synthetic Slice-6 timeline), `classifyDef` coverage of the full roster
including `medieval_spearman`, mode-transition matrix, and the probe's verdict-key regex set.

---

## Verification conventions (extend Phase 4)

- `python -m pytest tests -q` (scoped; never bare `python -m pytest -q`).
- `python tests/check_lua_syntax.py` (Phase 5 files auto-included: `scripts/*.lua`,
  `units/*.lua`, `luarules/gadgets/*.lua`, `gamedata/*.lua`).
- Per-slice headless probes via `tools/launch/run_phase5_sliceN_probe.py`, each emitting
  deterministic `*-verdict PASS` lines, with evidence versioned under `docs/` (runtime
  `infolog.txt` remains git-ignored).
- Slice 6 is the terminal integration probe and doubles as the Phase 5 acceptance gate.

## Probe run budget

The headless sim runs below realtime (~16–28 f/s observed in Phase 4). Budget each slice's slowest
stage: Slice 1 milestone verdicts through f≈120, Slice 3 haul at f≈90, Slice 4 heal tick at f≈120,
Slice 5 stance at f≈120. Slice 6 must reach a full `tc_destruction` including a catapult's initial
`reloadtime = 5.0` (150 frames) — allow 120 s wall clock and rely on the runner timeout plus log
tail, as Phase 4's `720:quitforce` does not reliably terminate the engine build.

## Scope boundaries

**In scope:**
- Victory/defeat engine: conquest, TC-destruction, regicide (new `medieval_king` unit reusing
  existing art), surrender command.
- Medieval HUD widget (text/primitives only) and the synced params it renders.
- Market building, elastic barter rates (no gold resource), cart trade routes.
- Town Center / Tower garrison shelter, healing, and archer-scaled defensive output.
- Cavalry charge, spearman brace, flank damage, defensive stance, single damage pipeline.
- Full automated skirmish match end-to-end probe to `GameOver` verdict.

**Out of scope:**
- A fifth "gold" resource (barter operates on the existing 4-resource pool).
- New art assets beyond 0 A.D. CC-BY-SA conversions; no BAR CC-BY-NC-ND assets; HUD is font-only.
- New hero meshes/textures for `medieval_king` — it reuses an existing converted model.
- Multiplayer netplay/lobby balance, latency compensation, spectator syncing of the HUD.
- Full diplomacy beyond ally-team elimination; morale/weather/terrain-slope charge effects.
- Save/load or mid-match resync of victory and garrison state.
- True per-archer dynamic projectile count (engine weapondef limitation, mapped to a damage
  multiplier in Slice 4).
- Balance tuning pass — the constants above are starting design values, tuned after all slices land.