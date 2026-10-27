"""Tests for audio FX hooks wiring and cooldown helpers (Point 3 polish audit).

Verifies:
1. GG.MedievalFX exports exist (PlayGather, PlayHaul, PlayConstruct, PlayUnderAttack).
2. Rate-limiting / cooldown logic prevents audio spam across successive calls.
3. Sound mapping matches expected assets:
   - wood -> sounds/economy/wood_chop.ogg
   - stone / iron -> sounds/economy/stone_mine.ogg
   - haul -> sounds/economy/haul_cart.ogg
   - construct -> sounds/economy/construction.ogg
   - under-attack -> sounds/ui/alarm_under_attack.ogg
4. Under-attack cooldown is isolated per-team.
5. Audio muting (medievalaudio = 0) silences all audio hooks.
6. Gather, hauling, and tactics gadgets wire to the GG.MedievalFX endpoints.
"""

from pathlib import Path
import unittest

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parent.parent

FX_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_fx.lua"
GATHER_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_gather.lua"
HAUL_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_hauling.lua"
TACTICS_GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_tactics.lua"

FX_HARNESS = r"""
GADGET_SRC = io.open(ROOT_PATH .. "/luarules/gadgets/gadget_medieval_fx.lua", "r"):read("*a")

MODOPTIONS = { medievalaudio = MODOPTION_VALUE }
SOUND_CALLS = {}
ECHO_CALLS = {}
GAME_FRAME = 0

Spring = {
  GetModOptions = function() return MODOPTIONS end,
  GetGameFrame = function() return GAME_FRAME end,
  PlaySoundFile = function(path, vol, x, y, z)
    SOUND_CALLS[#SOUND_CALLS + 1] = { path = path, vol = vol, x = x, y = y, z = z }
    return true
  end,
  Echo = function(text) ECHO_CALLS[#ECHO_CALLS + 1] = text end,
  SetGameRulesParam = function(key, val) end,
}

UnitDefs = {}
gadgetHandler = { IsSyncedCode = function() return true end }
GG = {}
gadget = {}

assert(load(GADGET_SRC, "@gadget_medieval_fx.lua", "t", _G))()

function SetFrame(f) GAME_FRAME = f end
function ClearCalls() SOUND_CALLS = {} end
function CallCount() return #SOUND_CALLS end
function LastCall() return SOUND_CALLS[#SOUND_CALLS] end
"""


class TestAudioFxWiring(unittest.TestCase):
    def _boot_fx(self, modoption=None):
        lua = LuaRuntime(unpack_returned_tuples=True)
        lua.globals().ROOT_PATH = str(ROOT).replace("\\", "/")
        lua.globals().MODOPTION_VALUE = modoption
        lua.execute(FX_HARNESS)
        return lua

    def test_sound_files_exist_on_disk(self):
        expected_files = [
            "sounds/economy/wood_chop.ogg",
            "sounds/economy/stone_mine.ogg",
            "sounds/economy/haul_cart.ogg",
            "sounds/economy/construction.ogg",
            "sounds/ui/alarm_under_attack.ogg",
            "sounds/ui/building_complete.ogg",
            "sounds/ui/unit_select.ogg",
        ]
        for rel in expected_files:
            p = ROOT / rel
            self.assertTrue(p.is_file(), f"Expected sound file missing: {rel}")

    def test_gg_medieval_fx_exports_exist(self):
        lua = self._boot_fx(1)
        self.assertTrue(lua.eval("type(GG.MedievalFX.PlayGather) == 'function'"))
        self.assertTrue(lua.eval("type(GG.MedievalFX.PlayHaul) == 'function'"))
        self.assertTrue(lua.eval("type(GG.MedievalFX.PlayConstruct) == 'function'"))
        self.assertTrue(lua.eval("type(GG.MedievalFX.PlayUnderAttack) == 'function'"))

    def test_gather_sound_mapping(self):
        lua = self._boot_fx(1)
        # Wood
        lua.execute("SetFrame(100)")
        res = lua.eval("GG.MedievalFX.PlayGather('wood')")
        self.assertTrue(res)
        last = lua.eval("LastCall()")
        self.assertEqual(last["path"], "sounds/economy/wood_chop.ogg")

        # Stone
        lua.execute("SetFrame(200)")
        res = lua.eval("GG.MedievalFX.PlayGather('stone')")
        self.assertTrue(res)
        last = lua.eval("LastCall()")
        self.assertEqual(last["path"], "sounds/economy/stone_mine.ogg")

        # Iron
        lua.execute("SetFrame(300)")
        res = lua.eval("GG.MedievalFX.PlayGather('iron')")
        self.assertTrue(res)
        last = lua.eval("LastCall()")
        self.assertEqual(last["path"], "sounds/economy/stone_mine.ogg")

        # Unsupported resource (e.g. food) plays nothing
        lua.execute("SetFrame(400)")
        before = lua.eval("CallCount()")
        res = lua.eval("GG.MedievalFX.PlayGather('food')")
        self.assertFalse(res)
        self.assertEqual(lua.eval("CallCount()"), before)

    def test_haul_and_construct_sound_mapping(self):
        lua = self._boot_fx(1)
        # Haul
        lua.execute("SetFrame(100)")
        res = lua.eval("GG.MedievalFX.PlayHaul()")
        self.assertTrue(res)
        last = lua.eval("LastCall()")
        self.assertEqual(last["path"], "sounds/economy/haul_cart.ogg")

        # Construct
        lua.execute("SetFrame(200)")
        res = lua.eval("GG.MedievalFX.PlayConstruct()")
        self.assertTrue(res)
        last = lua.eval("LastCall()")
        self.assertEqual(last["path"], "sounds/economy/construction.ogg")

    def test_under_attack_sound_mapping(self):
        lua = self._boot_fx(1)
        lua.execute("SetFrame(100)")
        res = lua.eval("GG.MedievalFX.PlayUnderAttack(0)")
        self.assertTrue(res)
        last = lua.eval("LastCall()")
        self.assertEqual(last["path"], "sounds/ui/alarm_under_attack.ogg")

    def test_gather_cooldown_rate_limiting(self):
        lua = self._boot_fx(1)
        lua.execute("SetFrame(100)")
        first = lua.eval("GG.MedievalFX.PlayGather('wood')")
        self.assertTrue(first)
        self.assertEqual(lua.eval("CallCount()"), 1)

        # Call again immediately (same frame): dropped
        second = lua.eval("GG.MedievalFX.PlayGather('wood')")
        self.assertFalse(second)
        self.assertEqual(lua.eval("CallCount()"), 1)

        # Call 15 frames later (0.5s): still in cooldown
        lua.execute("SetFrame(115)")
        third = lua.eval("GG.MedievalFX.PlayGather('wood')")
        self.assertFalse(third)
        self.assertEqual(lua.eval("CallCount()"), 1)

        # Call 40 frames later (>1.2s cooldown): should play
        lua.execute("SetFrame(140)")
        fourth = lua.eval("GG.MedievalFX.PlayGather('wood')")
        self.assertTrue(fourth)
        self.assertEqual(lua.eval("CallCount()"), 2)

    def test_gather_wood_and_stone_have_independent_cooldowns(self):
        lua = self._boot_fx(1)
        lua.execute("SetFrame(100)")
        self.assertTrue(lua.eval("GG.MedievalFX.PlayGather('wood')"))
        # Stone in same frame is not blocked by wood cooldown
        self.assertTrue(lua.eval("GG.MedievalFX.PlayGather('stone')"))
        self.assertEqual(lua.eval("CallCount()"), 2)

    def test_under_attack_cooldown_per_team(self):
        lua = self._boot_fx(1)
        lua.execute("SetFrame(100)")
        # Team 0 attacked
        self.assertTrue(lua.eval("GG.MedievalFX.PlayUnderAttack(0)"))
        # Team 0 attacked again in same frame: throttled
        self.assertFalse(lua.eval("GG.MedievalFX.PlayUnderAttack(0)"))

        # Team 1 attacked: distinct team, should play
        self.assertTrue(lua.eval("GG.MedievalFX.PlayUnderAttack(1)"))

        # Advance 150 frames (5s): team 0 still in 10s cooldown
        lua.execute("SetFrame(250)")
        self.assertFalse(lua.eval("GG.MedievalFX.PlayUnderAttack(0)"))

        # Advance 350 frames (>10s): team 0 can alert again
        lua.execute("SetFrame(450)")
        self.assertTrue(lua.eval("GG.MedievalFX.PlayUnderAttack(0)"))

    def test_audio_disabled_by_modoption_mutes_all(self):
        lua = self._boot_fx(0)
        lua.execute("SetFrame(100)")
        self.assertFalse(lua.eval("GG.MedievalFX.PlayGather('wood')"))
        self.assertFalse(lua.eval("GG.MedievalFX.PlayHaul()"))
        self.assertFalse(lua.eval("GG.MedievalFX.PlayConstruct()"))
        self.assertFalse(lua.eval("GG.MedievalFX.PlayUnderAttack(0)"))
        self.assertEqual(lua.eval("CallCount()"), 0)

    def test_gather_gadget_calls_fx_gather(self):
        content = GATHER_GADGET_PATH.read_text(encoding="utf-8")
        self.assertIn("GG.MedievalFX", content)
        self.assertIn("PlayGather", content)

    def test_hauling_gadget_calls_fx_haul(self):
        content = HAUL_GADGET_PATH.read_text(encoding="utf-8")
        self.assertIn("GG.MedievalFX", content)
        self.assertIn("PlayHaul", content)

    def test_tactics_gadget_calls_fx_under_attack(self):
        content = TACTICS_GADGET_PATH.read_text(encoding="utf-8")
        self.assertIn("GG.MedievalFX", content)
        self.assertIn("PlayUnderAttack", content)


if __name__ == "__main__":
    unittest.main()
