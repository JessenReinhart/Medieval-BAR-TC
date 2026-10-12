"""Phase 7 Slice 4 tests: lightweight LUS piece animation & motion dynamics.

Validates that the six Slice 4 unit scripts implement procedural animation in
pure LUS and stay backward-compatible with the single-piece converted meshes:

1. Every script compiles in bare Lua and exports the animation call-ins
   (`Create`, `StartMoving`, `StopMoving`, `Killed`, plus `AimWeapon1` /
   `FireWeapon1` on the armed units).
2. Piece access is defensive: optional sub-pieces are resolved through
   `optPiece()` (a `pcall(piece, name)` probe) and fall back to the root `base`
   piece, and every `Turn` / `Move` / `Spin` / `StopSpin` goes through
   `safeCall()` so a missing engine call-in cannot break a call-in.
3. The threading contract of `luarules/gadgets/unit_script.lua` is respected:
   `StartMoving` / `StopMoving` are not thread-wrapped, so the cadence loops are
   spawned with `StartThread`, while `Killed` (which *is* wrapped) holds the
   death tumble with `Sleep`.
4. Behaviour is exercised for real in a Lua sandbox that stubs the piece
   animation call-ins: the scripts run on a single-piece mesh (only `base`
   available) without error, animate the root piece, advance their cadence
   loops across frames, and use real sub-pieces when the mesh provides them.
5. Per-unit motion is distinct: melee thrust, bow draw/release, cavalry gallop,
   catapult arm swing-and-stop, villager labour swing, cart axle rumble.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
UNITS_DIR = ROOT / "units"

# script file -> unit def, whether it carries weapons, and the optional
# sub-pieces a fully rigged version of its mesh would expose.
SLICE_SPECS = {
    "medieval_infantry.lua": {
        "unit": "medieval_infantry",
        "combat": True,
        "subpieces": ("torso", "weapon"),
        "work_callin": None,
    },
    "medieval_archer.lua": {
        "unit": "medieval_archer",
        "combat": True,
        "subpieces": ("torso", "weapon"),
        "work_callin": None,
    },
    "medieval_cavalry.lua": {
        "unit": "medieval_cavalry",
        "combat": True,
        "subpieces": ("torso", "weapon"),
        "work_callin": None,
    },
    "medieval_catapult.lua": {
        "unit": "medieval_catapult",
        "combat": True,
        "subpieces": ("arm", "torso", "wheel"),
        "work_callin": None,
    },
    "medieval_villager.lua": {
        "unit": "medieval_villager",
        "combat": False,
        "subpieces": ("torso", "weapon"),
        "work_callin": "StartBuilding",
    },
    "medieval_cart.lua": {
        "unit": "medieval_cart",
        "combat": False,
        "subpieces": ("torso", "axle", "wheel"),
        "work_callin": None,
    },
}

COMMON_CALLINS = (
    "script.Create",
    "script.StartMoving",
    "script.StopMoving",
    "script.Killed",
)

COMBAT_CALLINS = (
    "script.AimFromWeapon1",
    "script.QueryWeapon1",
    "script.AimWeapon1",
    "script.FireWeapon1",
    "script.AimFromWeapon",
    "script.QueryWeapon",
    "script.AimWeapon",
    "script.FireWeapon",
)

# Animation call-ins the scripts must never invoke directly.
DIRECT_ANIM_CALLS = ("Turn", "Move", "Spin", "StopSpin")

# Stubs for the piece animation API. `AVAILABLE` is injected by the test: it
# lists the pieces the simulated mesh exposes, so the same script can be run
# against a single-piece hull and against a fully rigged one.
HARNESS = """
local H = {}
H.reset = function()
  H.turns, H.moves, H.spins, H.stopspins = {}, {}, {}, {}
  H.signals, H.masks, H.params, H.log = {}, {}, {}, {}
  H.pieceRequests, H.threads = {}, {}
  H.sleeps, H.threadCount = 0, 0
end
H.reset()

local function record(list, piece, axis, value, speed)
  list[#list + 1] = { piece = piece, axis = axis, value = value, speed = speed }
end

function piece(...)
  local names = { ... }
  local out = {}
  for i = 1, #names do
    local n = names[i]
    H.pieceRequests[#H.pieceRequests + 1] = n
    if not AVAILABLE[n] then error("piece not found: " .. tostring(n), 2) end
    out[i] = n
  end
  return table.unpack(out)
end

function Turn(p, axis, angle, speed) record(H.turns, p, axis, angle, speed) end
function Move(p, axis, dist, speed) record(H.moves, p, axis, dist, speed) end
function Spin(p, axis, speed, accel) record(H.spins, p, axis, speed, accel) end
function StopSpin(p, axis) record(H.stopspins, p, axis, 0, 0) end
function Signal(mask)
  H.signals[#H.signals + 1] = mask
  -- Mirror the framework: cancel every live thread whose signal mask overlaps.
  for i = 1, #H.threads do
    local t = H.threads[i]
    if not t.done and t.mask and (t.mask & mask) ~= 0 then
      t.done = true
      t.cancelled = true
    end
  end
end

function SetSignalMask(mask)
  H.masks[#H.masks + 1] = mask
  if H.running then H.running.mask = mask end
end

function Sleep(ms)
  H.sleeps = H.sleeps + 1
  coroutine.yield()
end

function StartThread(fn, ...)
  local co = coroutine.create(fn)
  H.threadCount = H.threadCount + 1
  -- A spawned thread inherits the signal mask of its parent, as the engine does.
  local t = {
    co = co,
    done = false,
    ret = nil,
    mask = H.running and H.running.mask or nil,
    cancelled = false,
  }
  H.threads[#H.threads + 1] = t
  local prev = H.running
  H.running = t
  local ok, ret = coroutine.resume(co, ...)
  H.running = prev
  if not ok then error(ret) end
  if coroutine.status(co) == "dead" then
    t.done = true
    t.ret = ret
  end
  return co
end

-- Mirrors the engine, which thread-wraps Create / Killed / AimWeapon /
-- FireWeapon but NOT StartMoving / StopMoving.
function H.startScriptThread(name, ...)
  local fn = script[name]
  if not fn then error("missing callin: " .. tostring(name)) end
  return StartThread(fn, ...)
end

Spring = {
  Echo = function(msg) H.log[#H.log + 1] = msg end,
  SetUnitRulesParam = function(id, name, value) H.params[name] = value end,
}

x_axis, y_axis, z_axis = 1, 2, 3
unitID = 7

function H.call(name, ...)
  local fn = script[name]
  if not fn then return nil end
  return fn(...)
end

function H.step(times)
  times = times or 1
  for _ = 1, times do
    for i = 1, #H.threads do
      local t = H.threads[i]
      if not t.done and coroutine.status(t.co) ~= "dead" then
        local prev = H.running
        H.running = t
        local ok, ret = coroutine.resume(t.co)
        H.running = prev
        if not ok then error(ret) end
        if coroutine.status(t.co) == "dead" then
          t.done = true
          t.ret = ret
        end
      end
    end
  end
end

function H.threadResult(i)
  local t = H.threads[i]
  return t and t.ret or nil
end

function H.alive()
  local n = 0
  for i = 1, #H.threads do
    if not H.threads[i].done then n = n + 1 end
  end
  return n
end

function H.drain(maxSteps)
  local guard = 0
  while H.alive() > 0 and guard < (maxSteps or 200) do
    H.step(1)
    guard = guard + 1
  end
  return guard
end

_G.H = H
"""


def _to_py(lua, value):
    """Recursively convert a Lua table into Python dicts/lists."""
    if lua.eval("type")(value) == "table":
        keys = list(value.keys())
        if not keys:
            return []
        if all(isinstance(k, int) for k in keys):
            return [_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _to_py(lua, value[k]) for k in keys}
    return value


class Sandbox:
    """Runs a unit script against stubbed piece animation call-ins."""

    def __init__(self, source: str, available=("base",)):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(HARNESS)
        # A name-keyed set of the pieces the simulated mesh exposes.
        self.lua.globals().AVAILABLE = self.lua.table(
            **{name: True for name in available}
        )
        self.lua.execute("script = {}")
        self.lua.execute(source)

    @property
    def h(self):
        return self.lua.globals().H

    def call(self, name, *args):
        return self.lua.globals().script[name](*args)

    def has(self, name):
        return self.lua.globals().script[name] is not None

    def start_thread(self, name, *args):
        return self.lua.globals().H.startScriptThread(name, *args)

    def thread_result(self, index=1):
        return self.lua.globals().H.threadResult(index)

    def records(self, key):
        return _to_py(self.lua, self.h[key])

    def step(self, times=1):
        self.h.step(times)

    def drain(self, max_steps=200):
        return self.h.drain(max_steps)

    def alive(self):
        return self.h.alive()

    def reset(self):
        self.h.reset()

    def targets(self, key="turns"):
        return {r["piece"] for r in self.records(key)}


def _function_body(source: str, header: str) -> str:
    """Source between a `function script.X` header and the next top-level header."""
    start = source.index(header)
    rest = source[start + len(header):]
    next_header = rest.find("\nfunction script.")
    body = rest if next_header == -1 else rest[:next_header]
    # Trim trailing comment banners so call-in bodies stay free of doc noise.
    return body


class Slice4SourceContractMixin:
    """Source-level contract shared by every Slice 4 script."""

    script_name = ""
    spec: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.path = SCRIPTS_DIR / cls.script_name
        cls.source = cls.path.read_text(encoding="utf-8")

    def test_script_exists_and_compiles(self):
        self.assertTrue(self.path.is_file(), f"missing {self.path}")
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().c = self.source
        result = lua.execute("local fn, err = load(c); return { fn = fn, err = err }")
        self.assertIsNotNone(result["fn"], f"Lua compile failure: {result['err']}")

    def test_exports_animation_callins(self):
        callins = COMMON_CALLINS + (COMBAT_CALLINS if self.spec["combat"] else ())
        for callin in callins:
            self.assertIn(callin, self.source, f"{self.script_name} missing {callin}")

    def test_root_base_piece_is_declared(self):
        # Both `piece "base"` and `piece('base')` are valid LUS spellings.
        self.assertRegex(
            self.source,
            r"""piece\s*(?:\(\s*['"]base['"]\s*\)|['"]base['"])""",
            f"{self.script_name} must declare the root base piece",
        )

    def test_optional_pieces_are_probed_not_required(self):
        # A rigged mesh may expose sub-pieces; a single-hull mesh may not. The
        # probe has to be a pcall so an unknown name never raises.
        self.assertIn("local function optPiece(name)", self.source)
        self.assertIn("pcall(piece, name)", self.source)
        self.assertIn("or base", self.source)

    def test_every_piece_transform_is_guarded(self):
        # `safeCall` must exist and be the only way the animation call-ins are
        # reached, so an engine without them degrades to a static model.
        self.assertIn("local function safeCall(fn, ...)", self.source)
        self.assertRegex(self.source, r"""type\(fn\) ~= ['"]function['"]""")
        for call in DIRECT_ANIM_CALLS:
            # `Turn(...)` etc. is a direct call; `safeCall(Turn, ...)` is not.
            # The negative lookbehind keeps `Spin` from matching `StopSpin`.
            self.assertNotRegex(
                self.source,
                rf"(?<![\w.])(?<!safeCall\(){call}\s*\(",
                f"{self.script_name} calls {call}() directly instead of safeCall({call}, ...)",
            )

    def test_signal_masks_are_declared_per_channel(self):
        # One distinct mask per channel, starting at 1.
        self.assertRegex(
            self.source,
            r"local SIG_MOVE,\s*SIG_[A-Z]+(?:\s*,\s*SIG_[A-Z]+)?\s*=\s*1,\s*\d",
            f"{self.script_name} must declare one signal mask per animation channel",
        )

    def test_start_moving_spawns_the_cadence_loop(self):
        # StartMoving is not thread-wrapped by the framework, so it must spawn
        # its own loop and must never Sleep in its own body.
        body = _function_body(self.source, "function script.StartMoving(")
        self.assertIn("StartThread", body)
        self.assertIn("SetSignalMask(SIG_MOVE)", body)
        self.assertIn("Sleep(", body)
        self.assertNotRegex(body, r"(?<!safeCall\()\bTurn\(")
        self.assertIn("safeCall(", body)

    def test_stop_moving_signals_and_resets(self):
        body = _function_body(self.source, "function script.StopMoving(")
        self.assertIn("Signal(SIG_MOVE)", body)
        self.assertNotIn("Sleep(", body)
        self.assertIn("restPose", body)

    def test_killed_runs_a_death_tumble(self):
        header = "function script.Killed(recentDamage, maxHealth)"
        self.assertIn(header, self.source)
        body = _function_body(self.source, header)
        # Killed *is* thread-wrapped, so it holds the collapse with Sleep before
        # handing the wreck level back to the engine.
        self.assertIn("Sleep(", body)
        self.assertIn("Signal(SIG_MOVE)", body)
        self.assertIn("SetSignalMask(SIG_DEATH)", body)
        self.assertRegex(body, r"safeCall\(Turn,\s*\w+,\s*z_axis")
        self.assertIn("return 1", body)


class Slice4SandboxMixin:
    """Behavioural contract, exercised against stubbed animation call-ins."""

    script_name = ""
    spec: dict = {}

    @classmethod
    def setUpClass(cls):
        cls.path = SCRIPTS_DIR / cls.script_name
        cls.source = cls.path.read_text(encoding="utf-8")

    def single_piece(self):
        return Sandbox(self.source, available=("base",))

    def rigged(self):
        return Sandbox(self.source, available=("base",) + tuple(self.spec["subpieces"]))

    def test_runs_on_a_single_piece_mesh(self):
        sb = self.single_piece()
        sb.call("Create")
        self.assertEqual(sb.targets("turns"), {"base"})
        self.assertTrue(sb.records("turns"), "Create must settle the model into its rest pose")

    def test_cadence_loop_advances_across_frames(self):
        sb = self.single_piece()
        sb.call("Create")
        before = len(sb.records("turns")) + len(sb.records("moves"))
        sb.call("StartMoving")
        self.assertEqual(sb.h.threadCount, 1, "StartMoving must spawn exactly one cadence thread")
        sb.step(1)
        first = sb.records("turns") + sb.records("moves")
        self.assertGreater(len(first), before, "the stride loop must animate on its first frame")
        sb.step(4)
        values = [r["value"] for r in sb.records("turns") + sb.records("moves")]
        nonzero = [v for v in values if v]
        self.assertTrue(nonzero, "the cadence loop must produce a visible displacement")
        self.assertGreater(len(set(values)), 1, "the cadence loop must cycle through poses")
        self.assertGreater(sb.alive(), 0, "the cadence loop must stay alive until StopMoving")

    def test_stop_moving_signals_the_loop_and_rests(self):
        sb = self.single_piece()
        sb.call("StartMoving")
        sb.step(2)
        sb.call("StopMoving")
        self.assertIn(1, sb.records("signals"), "StopMoving must signal the SIG_MOVE channel")
        self.assertFalse(sb.records("signals") is None)
        tail = sb.records("turns")[-3:]
        self.assertTrue(
            all(r["value"] == 0 for r in tail),
            "StopMoving must return the model to its rest pose",
        )

    def test_killed_tumble_holds_then_returns_wreck_level(self):
        sb = self.single_piece()
        sb.call("Create")
        sb.start_thread("Killed", 40, 100)
        self.assertGreater(sb.h.sleeps, 0, "Killed must Sleep so the engine holds the tumble")
        sb.drain()
        self.assertEqual(sb.alive(), 0, "the death tumble must finish")
        self.assertEqual(
            sb.thread_result(1), 1, "Killed must return the wreck level to the engine"
        )

    def test_uses_real_subpieces_when_the_mesh_has_them(self):
        rigged = self.rigged()
        rigged.call("Create")
        rigged.call("StartMoving")
        rigged.step(4)
        action = "FireWeapon1" if self.spec["combat"] else self.spec["work_callin"]
        if action:
            rigged.call(action)
            rigged.step(4)
        targets = set()
        for key in ("turns", "moves", "spins", "stopspins"):
            targets |= rigged.targets(key)
        self.assertTrue(
            targets & set(self.spec["subpieces"]),
            f"{self.script_name} must animate its sub-pieces when they exist, got {targets}",
        )

    def test_no_direct_animation_call_escapes_the_guard(self):
        # A transform on a piece the mesh does not have would raise at runtime;
        # the sandbox only exposes `base`, so any unguarded call would surface.
        sb = self.single_piece()
        sb.call("Create")
        sb.call("StartMoving")
        sb.step(6)
        sb.call("StopMoving")
        sb.start_thread("Killed", 90, 100)
        sb.drain()
        self.assertEqual(sb.alive(), 0)


class TestInfantryAnimation(Slice4SourceContractMixin, Slice4SandboxMixin, unittest.TestCase):
    script_name = "medieval_infantry.lua"
    spec = SLICE_SPECS["medieval_infantry.lua"]

    def test_melee_thrust_on_fire(self):
        body = _function_body(self.source, "function script.FireWeapon1(")
        self.assertIn("StartThread", body)
        self.assertIn("Sleep(", body)
        self.assertIn("safeCall(Move, weapon, z_axis", body)
        sb = self.single_piece()
        sb.call("Create")
        before = len(sb.records("moves"))
        sb.call("FireWeapon1")
        sb.step(1)
        moves = sb.records("moves")[before:]
        self.assertTrue(moves, "FireWeapon1 must drive the weapon piece")
        self.assertTrue(any(m["value"] for m in moves), "the thrust must displace the weapon")
        sb.drain()
        self.assertEqual(sb.alive(), 0, "the attack animation must complete")

    def test_aim_pitch_leans_the_torso(self):
        sb = self.single_piece()
        sb.reset()
        self.assertTrue(sb.call("AimWeapon1", 0.4, 0.25))
        self.assertTrue(sb.records("turns"), "AimWeapon1 must pitch the torso onto the aim line")
        sb.reset()
        # An absurd pitch is clamped rather than tipping the model over.
        self.assertTrue(sb.call("AimWeapon1", 0.0, 9.0))
        self.assertTrue(all(abs(r["value"]) <= 0.2 for r in sb.records("turns")))

    def test_unnumbered_weapon_callins_animate_too(self):
        sb = self.single_piece()
        sb.reset()
        self.assertTrue(sb.call("AimWeapon", 1, 0.0, 0.1))
        self.assertTrue(sb.records("turns"))
        sb.call("FireWeapon", 1)
        sb.drain()
        self.assertEqual(sb.alive(), 0)


class TestArcherAnimation(Slice4SourceContractMixin, Slice4SandboxMixin, unittest.TestCase):
    script_name = "medieval_archer.lua"
    spec = SLICE_SPECS["medieval_archer.lua"]

    def test_bow_draw_then_release(self):
        body = _function_body(self.source, "function script.FireWeapon1(")
        self.assertIn("StartThread", body)
        self.assertIn("Sleep(", body)
        # Draw pulls the bow back (negative) before the release snaps forward.
        self.assertRegex(body, r"safeCall\(Move,\s*weapon,\s*z_axis,\s*-\d")
        sb = self.single_piece()
        sb.call("Create")
        sb.call("FireWeapon1")
        sb.step(1)
        draw = [m["value"] for m in sb.records("moves")]
        self.assertTrue(any(v < 0 for v in draw), "the draw must pull the bow arm back")
        sb.step(3)
        sb.drain()
        release = [m["value"] for m in sb.records("moves")]
        self.assertTrue(any(v > 0 for v in release), "the release must snap the bow forward")
        self.assertEqual(sb.alive(), 0)

    def test_gait_is_lighter_than_infantry(self):
        archer = Sandbox(self.source, available=("base",))
        archer.call("StartMoving")
        archer.step(4)
        archer_peak = max(
            abs(r["value"]) for r in archer.records("turns") + archer.records("moves")
        )
        infantry_source = (SCRIPTS_DIR / "medieval_infantry.lua").read_text(encoding="utf-8")
        infantry = Sandbox(infantry_source, available=("base",))
        infantry.call("StartMoving")
        infantry.step(4)
        infantry_peak = max(
            abs(r["value"]) for r in infantry.records("turns") + infantry.records("moves")
        )
        self.assertLess(archer_peak, infantry_peak, "the archer jog must be shallower than the infantry stride")


class TestCavalryAnimation(Slice4SourceContractMixin, Slice4SandboxMixin, unittest.TestCase):
    script_name = "medieval_cavalry.lua"
    spec = SLICE_SPECS["medieval_cavalry.lua"]

    def test_gallop_cycle_is_deeper_than_a_stride(self):
        self.assertIn("GALLOP", self.source)
        cavalry = Sandbox(self.source, available=("base",))
        cavalry.call("StartMoving")
        cavalry.step(4)
        cavalry_peak = max(r["value"] for r in cavalry.records("moves"))
        infantry_source = (SCRIPTS_DIR / "medieval_infantry.lua").read_text(encoding="utf-8")
        infantry = Sandbox(infantry_source, available=("base",))
        infantry.call("StartMoving")
        infantry.step(4)
        infantry_peak = max(r["value"] for r in infantry.records("moves"))
        self.assertGreater(cavalry_peak, infantry_peak, "the horse gallop must lift higher than a footfall")

    def test_gallop_rocks_forward_and_back(self):
        sb = self.single_piece()
        sb.call("StartMoving")
        sb.step(4)
        pitches = [r["value"] for r in sb.records("turns") if r["axis"] == 1]
        self.assertTrue(any(v > 0 for v in pitches), "the gallop must pitch forward")
        self.assertTrue(any(v < 0 for v in pitches), "the gallop must pitch back")

    def test_lance_thrust_on_fire(self):
        body = _function_body(self.source, "function script.FireWeapon1(")
        self.assertIn("safeCall(Move, weapon, z_axis", body)
        self.assertIn("Sleep(", body)
        sb = self.single_piece()
        sb.call("Create")
        sb.call("FireWeapon1")
        sb.step(1)
        self.assertTrue(any(m["value"] < 0 for m in sb.records("moves")), "the charge must gather the lance")
        sb.drain()
        self.assertTrue(any(m["value"] > 0 for m in sb.records("moves")), "the charge must drive the lance through")
        self.assertEqual(sb.alive(), 0)


class TestCatapultAnimation(Slice4SourceContractMixin, Slice4SandboxMixin, unittest.TestCase):
    script_name = "medieval_catapult.lua"
    spec = SLICE_SPECS["medieval_catapult.lua"]

    def test_arm_piece_and_angles_are_declared(self):
        self.assertIn('optPiece("arm")', self.source)
        self.assertIn("ARM_REST, ARM_DRAWN", self.source)

    def test_aim_winds_the_arm_back(self):
        sb = self.single_piece()
        sb.reset()
        # The dead-zone guard needs a target; an unobservable target is treated
        # as in range so combat never stalls.
        self.assertTrue(sb.call("AimWeapon1", 0.0, 0.1))
        self.assertTrue(
            any(r["value"] < 0 for r in sb.records("turns")),
            "AimWeapon1 must winch the arm back off the rest angle",
        )

    def test_fire_swings_the_arm_and_stops_it(self):
        body = _function_body(self.source, "function script.FireWeapon1(")
        self.assertIn("StartThread", body)
        self.assertIn("Sleep(", body)
        self.assertIn("safeCall(Turn, arm, x_axis", body)
        sb = self.single_piece()
        sb.call("Create")
        sb.reset()
        sb.call("FireWeapon1")
        sb.step(1)
        flung = [r["value"] for r in sb.records("turns")]
        self.assertTrue(any(v > 0.5 for v in flung), "the arm must fling past the stop")
        sb.drain()
        arrested = [r["value"] for r in sb.records("turns")]
        self.assertTrue(any(0 < v < 0.7 for v in arrested), "the stop must arrest the arm")
        self.assertEqual(sb.alive(), 0)

    def test_catapult_creeps_and_spins_its_wheels(self):
        sb = self.single_piece()
        sb.call("Create")
        sb.reset()
        sb.call("StartMoving")
        sb.step(2)
        self.assertTrue(sb.records("turns"), "the chassis must lurch while the engine creeps")
        # A single-piece mesh has no wheel to rotate: spinning the root piece
        # would tumble the whole engine, so the spin must be skipped.
        self.assertFalse(sb.records("spins"), "the root piece must never be spun")
        self.assertFalse(sb.records("stopspins"))
        sb.call("StopMoving")

        rigged = self.rigged()
        rigged.call("Create")
        rigged.call("StartMoving")
        rigged.step(2)
        self.assertTrue(rigged.records("spins"), "a real wheel piece must spin")
        rigged.call("StopMoving")
        self.assertTrue(rigged.records("stopspins"), "StopMoving must stop the wheel spin")

    def test_wreck_stops_the_wheels(self):
        body = _function_body(self.source, "function script.Killed(")
        self.assertIn("StopSpin", body)
        self.assertIn("hasWheel", body)

    def test_dead_zone_guard_still_refuses_point_blank_targets(self):
        # Slice 4 must not weaken the Slice 4-of-Phase-4 dead zone contract.
        self.assertIn("local MIN_RANGE = 120", self.source)
        self.assertIn("targetBeyondDeadZone", self.source)


class TestVillagerAnimation(Slice4SourceContractMixin, Slice4SandboxMixin, unittest.TestCase):
    script_name = "medieval_villager.lua"
    spec = SLICE_SPECS["medieval_villager.lua"]

    def test_build_callins_are_exported(self):
        for callin in ("script.StartBuilding", "script.StopBuilding"):
            self.assertIn(callin, self.source)

    def test_labour_loop_swings_the_tool(self):
        body = _function_body(self.source, "function script.StartBuilding(")
        self.assertIn("StartThread", body)
        self.assertIn("SetSignalMask(SIG_WORK)", body)
        self.assertIn("Sleep(", body)
        sb = self.single_piece()
        sb.call("Create")
        sb.call("StartBuilding")
        sb.step(1)
        raise_phase = [r["value"] for r in sb.records("turns")]
        self.assertTrue(any(v < 0 for v in raise_phase), "the tool must be raised first")
        sb.step(2)
        self.assertTrue(any(v > 0 for v in [r["value"] for r in sb.records("turns")]), "the tool must strike down")
        sb.call("StopBuilding")
        self.assertIn(2, sb.records("signals"), "StopBuilding must signal the SIG_WORK channel")

    def test_labour_loop_keeps_working_across_frames(self):
        sb = self.single_piece()
        sb.call("StartBuilding")
        sb.step(8)
        self.assertGreater(sb.alive(), 0, "the labour cadence must keep running until StopBuilding")
        self.assertGreaterEqual(sb.h.sleeps, 4)


class TestCartAnimation(Slice4SourceContractMixin, Slice4SandboxMixin, unittest.TestCase):
    script_name = "medieval_cart.lua"
    spec = SLICE_SPECS["medieval_cart.lua"]

    def test_hauling_marker_is_preserved(self):
        # Phase 4 Slice 5 contract: the probe reads this rules param back.
        self.assertIn('HAULING_PARAM = "medieval_cart_hauling"', self.source)

    def test_hauling_param_tracks_motion(self):
        sb = self.single_piece()
        sb.call("Create")
        self.assertEqual(sb.records("params")["medieval_cart_hauling"], 0)
        sb.call("StartMoving")
        self.assertEqual(sb.records("params")["medieval_cart_hauling"], 1)
        sb.call("StopMoving")
        self.assertEqual(sb.records("params")["medieval_cart_hauling"], 0)

    def test_axle_rumble_and_wheel_spin(self):
        sb = self.single_piece()
        sb.call("StartMoving")
        sb.step(2)
        self.assertTrue(sb.records("turns"), "the cart body must rumble while hauling")
        # A single-piece mesh has no wheel to rotate: spinning the root piece
        # would tumble the whole cart, so the spin must be skipped.
        self.assertFalse(sb.records("spins"), "the root piece must never be spun")
        sb.call("StopMoving")

        rigged = self.rigged()
        rigged.call("StartMoving")
        rigged.step(2)
        self.assertTrue(rigged.records("spins"), "a real wheel piece must spin while hauling")
        rigged.call("StopMoving")
        self.assertTrue(rigged.records("stopspins"), "StopMoving must stop the wheel spin")

    def test_wreck_tips_over_and_clears_the_marker(self):
        body = _function_body(self.source, "function script.Killed(")
        self.assertIn("setHauling(0)", body)
        self.assertIn("Sleep(", body)
        sb = self.single_piece()
        sb.call("StartMoving")
        sb.start_thread("Killed", 60, 100)
        sb.drain()
        self.assertEqual(sb.alive(), 0)
        self.assertEqual(sb.records("params")["medieval_cart_hauling"], 0)


class TestSlice4CrossCutting(unittest.TestCase):
    """Repo-level checks: bindings, no direct engine calls, distinct motion."""

    def test_every_slice_script_is_bound_to_its_unit_def(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        for script_name, spec in SLICE_SPECS.items():
            unit_path = UNITS_DIR / f"{spec['unit']}.lua"
            self.assertTrue(unit_path.is_file(), f"missing {unit_path}")
            table = lua.execute(unit_path.read_text(encoding="utf-8"))
            defn = _to_py(lua, table[spec["unit"]])
            self.assertEqual(
                defn.get("script"),
                script_name,
                f"{spec['unit']} must stay bound to {script_name}",
            )

    def test_animation_uses_no_engine_side_channels(self):
        # Slice 4 is pure LUS piece animation: no gadget, VFS or unit-def side
        # effects. The only rules-param writes allowed are the pre-existing
        # Phase 4 contracts, which live in a named local helper.
        allowed_helpers = ("local function publish(", "local function setHauling(")
        for script_name in SLICE_SPECS:
            source = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
            for token in ("GG.", "VFS.", "gadgetHandler", "UnitDefs"):
                self.assertNotIn(token, source, f"{script_name} must stay pure LUS")
            for match in re.finditer(r"Spring\.SetUnitRulesParam", source):
                head = source[: match.start()]
                helper_start = max(
                    head.rfind(helper) for helper in allowed_helpers
                )
                self.assertGreater(
                    helper_start,
                    -1,
                    f"{script_name} writes a rules param outside a pre-existing helper",
                )
                # The write must sit inside a named helper defined before any
                # call-in, i.e. it has not been smuggled into an animation
                # call-in body.
                self.assertGreater(
                    helper_start,
                    head.rfind("function script."),
                    f"{script_name} writes a rules param from an animation call-in",
                )

    def test_weapon_callins_still_resolve_to_base_piece(self):
        # Backward compatibility: the single-piece mesh must still be aimed
        # through the root piece on every armed Slice 4 unit.
        for script_name, spec in SLICE_SPECS.items():
            if not spec["combat"]:
                continue
            source = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
            for header in (
                "function script.AimFromWeapon1",
                "function script.QueryWeapon1",
                "function script.AimFromWeapon",
                "function script.QueryWeapon",
            ):
                body = _function_body(source, header)
                self.assertIn("return base", body, f"{script_name}: {header} must return base")

    def test_aim_and_fire_callins_return_the_engine_contract(self):
        for script_name, spec in SLICE_SPECS.items():
            if not spec["combat"]:
                continue
            source = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
            for header in ("function script.AimWeapon1", "function script.AimWeapon("):
                body = _function_body(source, header)
                self.assertIn("return true", body, f"{script_name}: {header} must clear angleGood")

    def test_units_animate_differently(self):
        # Each unit's cadence must be distinguishable, i.e. the slice is not one
        # copy-pasted loop: compare the per-unit cycle period and peak lift.
        signatures = {}
        for script_name in SLICE_SPECS:
            source = (SCRIPTS_DIR / script_name).read_text(encoding="utf-8")
            sb = Sandbox(source, available=("base",))
            sb.call("StartMoving")
            sb.step(4)
            moves = sb.records("moves")
            turns = sb.records("turns")
            signatures[script_name] = (
                round(max(r["value"] for r in moves), 3) if moves else 0.0,
                round(max(abs(r["value"]) for r in turns), 3) if turns else 0.0,
            )
        self.assertGreater(
            len(set(signatures.values())),
            len(signatures) - 2,
            f"the cadences are too similar to be per-unit motion: {signatures}",
        )


if __name__ == "__main__":
    unittest.main()
