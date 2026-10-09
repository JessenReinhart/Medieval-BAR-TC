# Slice 7 Probe Evidence (Recoil headless, run 2026-10-09)

Source of truth: `tools/launch/run_phase2_slice2_probe.py` -> `tools/runtime/infolog.txt`
(git-ignored; regenerated each run). Probe stages live in
`luarules/gadgets/gadget_phase2_test_forces.lua` after Slice 6 (frames 320-354).

## Engine def shape (why eligibility keys `canMove`, not `isBuilding`)

```
PHASE3 PROBE supply def-shape granary.isBuilding=false granary.canMove=false granary.speed=0 | infantry.isBuilding=false infantry.canMove=true infantry.speed=32
```

The engine reports `isBuilding=false` for `medieval_granary` (a static building) and for
`medieval_infantry` alike, so `def.isBuilding ~= true` cannot exclude buildings. `canMove`
correctly discriminates (`granary.canMove=false` vs `infantry.canMove=true`). Runtime tracking now
emits `PHASE3 SUPPLY tracked` only for `medieval_infantry` and `medieval_villager`; buildings are
no longer tracked as supply recipients.

## Deterministic Slice 7 verdicts (all PASS)

```
PHASE3 PROBE supply supplied-verdict f=326 PASS (inSupply=true count=1 endpointCount=1)
PHASE3 PROBE supply unsupplied-verdict f=326 PASS (far inSupply=false)
PHASE3 PROBE supply team-isolation-verdict f=326 PASS (enemy inSupply=false)
PHASE3 PROBE supply endpoint-count-verdict f=326 PASS (count=1 expect>=1)
PHASE3 PROBE supply damage-tech verdict f=330 PASS (ok=false researched=true mult=1.250)
PHASE3 PROBE supply damage-bonus verdict f=330 PASS (SupplyBonus=0.100 expect>0)
PHASE3 PROBE supply damage-stack f=330 team=0 tech=1.250 supply=0.100 combined=1.3750
PHASE3 PROBE gather selection-verdict f=345 PASS (picked=<far> expect_far=<far> remNear=500 remFar=500; target selection only)
PHASE3 PROBE supply restoration-verdict f=354 PASS (after road removal inSupply=false count=0)
```

Probe reached frame 354 (max simulated frame 354 in this run).

## Real outgoing damage (end-to-end UnitPreDamaged path)

```
PHASE3 SUPPLY damage attacker=7441 defender=15252 base=135.4 bonus=0.10 scaled=186.1
```

`135.4 * 1.25 (iron_swords) * 1.10 (supply) = 186.175`, matching `scaled=186.1`. This line is
emitted inside `gadget:UnitPreDamaged` during a real melee hit, confirming the two multipliers
stack multiplicatively in live combat (not just the Lua harness).

## Gather selection is target choice only (no waypoint routing)

The gather gadget selects a harvest node by cost and issues a single move; it does not route.
`AssignGather` picked the road-connected node 150 elmos away over a nearer (110 elmo) off-network
node because `150 < 110 * 1.5`. The verdict asserts the selected `nodeID`, nothing about a path.

## Caveats / remaining

- The only Lua error in the log is the pre-existing, pre-game
  `libs/s11n/feature_s11n.lua:186 SetFeatureMoveCtrl (number expected, got nil)` at `f=-1`; it is
  unrelated to Slice 7.
- Road removal is verified by reading supply state on frame 354, four frames after
  `Spring.DestroyFeature` at frame 350, because Spring defers `FeatureDestroyed` past the calling
  `GameFrame`.