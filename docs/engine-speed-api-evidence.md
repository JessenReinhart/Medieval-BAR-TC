# Engine Speed API Evidence

## Pinned Engine Version Identification
- Engine binary version: `2026.07.04 (Headless)`
- Verified from `tools/runtime/infolog.txt` (line 47: `Spring Engine Version: 2026.07.04 (Headless)`) and execution of `tools/engine/recoil_2026.07.04/spring-headless.exe --version`.
- Pinned upstream tag: `2026.07.04`
- Pinned upstream commit SHA: `de69361239d8c8b1012dba3f5aa3122954ea4da3`
  - GitHub API tag reference: `https://api.github.com/repos/beyond-all-reason/RecoilEngine/git/ref/tags/2026.07.04`
  - GitHub API tag object: `https://api.github.com/repos/beyond-all-reason/RecoilEngine/git/tags/9f414457061855b9f6f1caf5b4e4dda6694282af` pointing to commit `de69361239d8c8b1012dba3f5aa3122954ea4da3`.

## Local `.engine-src` Completeness Verdict
- `.engine-src` status: **Partial / Incomplete** (contains only 24 extracted C++ files).
- `LuaSyncedCtrl.cpp` presence: **Absent** (`Test-Path .engine-src/LuaSyncedCtrl.cpp` -> `False`).
- `LuaSyncedMoveCtrl.cpp` presence: **Absent** (`Test-Path .engine-src/LuaSyncedMoveCtrl.cpp` -> `False`).
- Verdict: Prior claims that `.engine-src` was complete were false. Its omission of `LuaSyncedCtrl.cpp` and `LuaSyncedMoveCtrl.cpp` reflects an incomplete local source dump, not the absence of the engine API.

## Upstream Pinned Source Inspection
- Upstream URLs for exact pinned commit `de69361239d8c8b1012dba3f5aa3122954ea4da3`:
  - `LuaSyncedCtrl.cpp`: `https://raw.githubusercontent.com/beyond-all-reason/RecoilEngine/de69361239d8c8b1012dba3f5aa3122954ea4da3/rts/Lua/LuaSyncedCtrl.cpp`
  - `LuaSyncedMoveCtrl.cpp`: `https://raw.githubusercontent.com/beyond-all-reason/RecoilEngine/de69361239d8c8b1012dba3f5aa3122954ea4da3/rts/Lua/LuaSyncedMoveCtrl.cpp`

### Registration Trace
1. In `rts/Lua/LuaSyncedCtrl.cpp`:
   - Line 18: `#include "LuaSyncedMoveCtrl.h"`
   - Line 395:
     ```cpp
     /*** @field Spring.MoveCtrl MoveCtrl */
     if (!LuaSyncedMoveCtrl::PushMoveCtrl(L))
         return false;
     ```
2. In `rts/Lua/LuaSyncedMoveCtrl.cpp`:
   - Line 39:
     ```cpp
     lua_pushliteral(L, "MoveCtrl");
     lua_createtable(L, 0, 32);
     ...
     REGISTER_LUA_CFUNC(SetAirMoveTypeData);
     REGISTER_LUA_CFUNC(SetGroundMoveTypeData);
     REGISTER_LUA_CFUNC(SetGunshipMoveTypeData);
     REGISTER_LUA_CFUNC(SetMoveDef);
     ...
     lua_rawset(L, -3);
     ```

## Verified Speed Mutator APIs
The prior claim that Recoil / Spring has "no engine speed mutator" is false.
Recoil exposes real runtime speed mutators directly on `Spring.MoveCtrl`:

### 1. `Spring.MoveCtrl.SetGroundMoveTypeData`
- **C++ implementation**: `LuaSyncedMoveCtrl::SetGroundMoveTypeData` -> `SetMoveTypeData(L, ParseDerivedMoveType<CGroundMoveType>(L, __func__, 1), __func__)`.
- **Supported call signatures**:
  - `Spring.MoveCtrl.SetGroundMoveTypeData(unitID, key, value)` -> returns number of assigned values (1 on success).
  - `Spring.MoveCtrl.SetGroundMoveTypeData(unitID, { key1 = val1, key2 = val2, ... })` -> returns number of assigned values.
- **Speed & movement keys supported (CGroundMoveType & AMoveType)**:
  - `maxSpeed` (number / float): Maximum speed in engine world units per second (elmos/sec). Note: 1 elmo/sec = 1/30 elmos/frame.
  - `maxWantedSpeed` (number / float): Maximum wanted speed.
  - `accRate` (number / float): Acceleration rate.
  - `decRate` (number / float): Deceleration rate.
  - `turnRate` (number / float): Turn rate.
  - `turnAccel` (number / float): Turn acceleration rate.
  - `maxReverseSpeed` (number / float): Maximum reverse speed.
  - `maxReverseDist` (number / float): Maximum distance to travel in reverse.
  - `minReverseAngle` (number / float): Minimum angle threshold for reversing.
  - `sqSkidSpeedMult` (number / float): Skid speed multiplier squared.
  - `pushResistant` (boolean): Whether unit resists physics push.
  - `useWantedSpeed[0]` (boolean): Use wanted speed for individual orders.
  - `useWantedSpeed[1]` (boolean): Use wanted speed for formation orders.

### 2. `Spring.MoveCtrl.SetAirMoveTypeData` / `Spring.MoveCtrl.SetGunshipMoveTypeData`
- Exposes corresponding `maxSpeed`, `maxWantedSpeed`, `accRate`, `decRate`, and aircraft/gunship-specific flight parameters for flying move types (`CStrafeAirMoveType`, `CHoverAirMoveType`).

### 3. `Spring.MoveCtrl.SetMoveDef`
- Signature: `Spring.MoveCtrl.SetMoveDef(unitID, moveDefNameOrID)` -> returns boolean.
- Dynamically swaps unit pathing definition, clearing PFS caches and resetting footprint / speed capabilities.

## Risks of Composition with Other Modifiers
1. **Engine vs Game-Globals (GG) Confusion**:
   - `Spring.MoveCtrl.SetGroundMoveTypeData` is a native C++ engine Lua API in synced scope (`LuaRules` / gadgets).
   - It is distinct from game-level Lua frameworks or GG tables (`GG.MoveControl`, `GG.SpeedModifiers`, etc.) often written in game rules.
2. **UnitScript / Animation interference**:
   - Setting `maxSpeed` mutates the physical move type, but model animation scripts (`StartMoving()`, walk loops) may calculate animation stride/tempo based on unitDef base speeds unless updated.
3. **Formation speed clamping (`useWantedSpeed[1]`)**:
   - If formation orders are active, formation controllers may govern or throttle individual speeds unless `useWantedSpeed[1]` is explicitly configured or commands are given as non-formation move orders.
4. **Permanent vs transient modification**:
   - `SetGroundMoveTypeData` mutates the live `CGroundMoveType` instance in memory. It persists until changed again or reset, unlike temporary slow/stun status effects. Any gadget altering `maxSpeed` must track original unit def speeds to restore or stack modifications deterministically.
