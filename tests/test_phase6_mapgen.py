"""Phase-6 tests: procedural map generation subsystem.

Layers under test:

1. Pure module — `scripts/medieval_mapgen.lua`:
   - Purity: zero Spring.*, VFS.*, or GG.* strings; no require().
   - Bare LuaRuntime execution with no globals injected.
   - Exports: newRNG, generate, FEATURES, DENSITY_SCALES, START_POCKET.
2. Determinism:
   - Same seed and inputs produce byte-identical feature layouts.
   - Different seeds produce divergent layouts.
3. Bounds & Clearance:
   - All features respect EDGE_MARGIN (128) boundary.
   - All features clear START_EXCLUSION_RADIUS (100) from every start position.
   - All features of the same type satisfy MIN_DIST spacing to avoid mesh overlap.
4. Fairness:
   - Each starting team receives a guaranteed resource pocket.
   - Every pocket contains all 4 resource types (tree, stone, iron, deer).
   - Resource counts match the M.START_POCKET specification (12 tree, 4 stone, 3 iron, 4 deer).
5. Density:
   - Total feature count scales strictly: sparse < normal < dense.
6. Totality & Robustness:
   - Nil, empty, partial, and malformed option tables never crash generate().
   - Invalid seed types, negative values, and floats handled cleanly by newRNG().
   - Out-of-spec density strings fall back gracefully to "normal".
7. Gadget Contract:
   - `luarules/gadgets/gadget_medieval_mapgen.lua` exists.
   - Synced code guard present.
   - Gated on `medievalmapgen` modoption.
   - Declares layer = 2.
   - Calls Spring.CreateFeature and Spring.GetGroundHeight.
   - Includes pure module via VFS.Include.
8. Modoptions:
   - `modoptions.lua` declares `medievalmapgen` (bool), `medievalmapgenseed` (number),
     and `medievalmapdensity` (list with sparse, normal, dense).
"""

import math
import re
import unittest
from pathlib import Path

from lupa import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "medieval_mapgen.lua"
GADGET_PATH = ROOT / "luarules" / "gadgets" / "gadget_medieval_mapgen.lua"
MODOPTIONS_PATH = ROOT / "modoptions.lua"

# Constants mirrored from scripts/medieval_mapgen.lua
EDGE_MARGIN = 128
START_EXCLUSION_RADIUS = 100
MIN_DIST = {
    "medieval_tree": 24,
    "medieval_stone": 36,
    "medieval_iron": 36,
    "medieval_deer": 30,
}
EXPECTED_FEATURES = {
    "TREE": "medieval_tree",
    "STONE": "medieval_stone",
    "IRON": "medieval_iron",
    "DEER": "medieval_deer",
}
EXPECTED_POCKET_COUNTS = {
    "medieval_tree": 12,
    "medieval_stone": 4,
    "medieval_iron": 3,
    "medieval_deer": 4,
}


def _lua_to_py(lua, value):
    """Recursively convert Lua tables to Python primitives."""
    if value is None:
        return None
    val_type = lua.eval("type")(value)
    if val_type == "table":
        keys = list(value.keys())
        if not keys:
            return []
        if all(isinstance(k, int) for k in keys):
            return [_lua_to_py(lua, value[i]) for i in range(1, len(keys) + 1)]
        return {k: _lua_to_py(lua, value[k]) for k in keys}
    return value


class MapgenBase(unittest.TestCase):
    """Base class creating a fresh LuaRuntime and module instance per test."""

    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.m = self.lua.execute(MODULE_PATH.read_text(encoding="utf-8"))

    def _make_starts(self, starts_list):
        tbl = self.lua.table()
        for idx, sp in enumerate(starts_list, start=1):
            entry = self.lua.table(x=sp[0], z=sp[1])
            tbl[idx] = entry
        return tbl


# ---------------------------------------------------------------------------
# 1. Purity & Exports
# ---------------------------------------------------------------------------


class TestMapgenPurity(MapgenBase):
    def setUp(self):
        super().setUp()
        self.source = MODULE_PATH.read_text(encoding="utf-8")

    def test_no_spring_calls(self):
        calls = re.findall(r"Spring\.[A-Za-z0-9_]+", self.source)
        self.assertEqual(calls, [], f"Disallowed Spring calls found: {calls}")

    def test_no_vfs_calls(self):
        calls = re.findall(r"VFS\.[A-Za-z0-9_]+", self.source)
        self.assertEqual(calls, [], f"Disallowed VFS calls found: {calls}")

    def test_no_gg_calls(self):
        calls = re.findall(r"GG\.[A-Za-z0-9_]+", self.source)
        self.assertEqual(calls, [], f"Disallowed GG calls found: {calls}")

    def test_no_require(self):
        self.assertNotIn("require(", self.source)
        self.assertNotIn("require '", self.source)
        self.assertNotIn('require "', self.source)

    def test_loads_in_bare_lua_runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        self.assertIsNone(lua.eval("Spring"))
        self.assertIsNone(lua.eval("VFS"))
        self.assertIsNone(lua.eval("GG"))
        mod = lua.execute(self.source)
        self.assertIsNotNone(mod)

    def test_exports_required_api(self):
        self.assertTrue(self.lua.eval("type")(self.m.newRNG) == "function")
        self.assertTrue(self.lua.eval("type")(self.m.generate) == "function")
        self.assertTrue(self.lua.eval("type")(self.m.FEATURES) == "table")
        self.assertTrue(self.lua.eval("type")(self.m.DENSITY_SCALES) == "table")

    def test_exported_features_table(self):
        features = _lua_to_py(self.lua, self.m.FEATURES)
        self.assertEqual(features, EXPECTED_FEATURES)

    def test_exported_density_scales(self):
        scales = _lua_to_py(self.lua, self.m.DENSITY_SCALES)
        self.assertEqual(scales, {"sparse": 0.6, "normal": 1.0, "dense": 1.6})


# ---------------------------------------------------------------------------
# 2. Determinism
# ---------------------------------------------------------------------------


class TestMapgenDeterminism(MapgenBase):
    def test_same_seed_identical_outputs(self):
        starts = self._make_starts([(800, 800), (3200, 3200)])
        opts1 = self.lua.table(mapSizeX=4096, mapSizeZ=4096, seed=12345, density="normal", startPositions=starts)
        opts2 = self.lua.table(mapSizeX=4096, mapSizeZ=4096, seed=12345, density="normal", startPositions=starts)

        res1 = _lua_to_py(self.lua, self.m.generate(opts1))
        res2 = _lua_to_py(self.lua, self.m.generate(opts2))

        self.assertEqual(len(res1["features"]), len(res2["features"]))
        self.assertEqual(res1["features"], res2["features"])
        self.assertEqual(res1["startPockets"], res2["startPockets"])

    def test_different_seeds_divergent_outputs(self):
        starts = self._make_starts([(800, 800), (3200, 3200)])
        opts1 = self.lua.table(mapSizeX=4096, mapSizeZ=4096, seed=12345, density="normal", startPositions=starts)
        opts2 = self.lua.table(mapSizeX=4096, mapSizeZ=4096, seed=99999, density="normal", startPositions=starts)

        res1 = _lua_to_py(self.lua, self.m.generate(opts1))
        res2 = _lua_to_py(self.lua, self.m.generate(opts2))

        self.assertNotEqual(res1["features"], res2["features"])

    def test_rng_determinism(self):
        rng1 = self.m.newRNG(777)
        rng2 = self.m.newRNG(777)

        seq1 = [rng1.random() for _ in range(50)]
        seq2 = [rng2.random() for _ in range(50)]
        self.assertEqual(seq1, seq2)

        rng3 = self.m.newRNG(888)
        seq3 = [rng3.random() for _ in range(50)]
        self.assertNotEqual(seq1, seq3)


# ---------------------------------------------------------------------------
# 3. Bounds & Clearance
# ---------------------------------------------------------------------------


class TestMapgenBoundsAndClearance(MapgenBase):
    def test_bounds_and_clearance(self):
        size_x, size_z = 4096, 4096
        start_pts = [(700, 700), (3300, 3300)]
        starts = self._make_starts(start_pts)

        opts = self.lua.table(
            mapSizeX=size_x,
            mapSizeZ=size_z,
            seed=42,
            density="normal",
            startPositions=starts,
        )
        res = _lua_to_py(self.lua, self.m.generate(opts))
        features = res["features"]

        self.assertGreater(len(features), 0)

        # 1. Bounds check
        for f in features:
            self.assertGreaterEqual(f["x"], EDGE_MARGIN)
            self.assertLessEqual(f["x"], size_x - EDGE_MARGIN)
            self.assertGreaterEqual(f["z"], EDGE_MARGIN)
            self.assertLessEqual(f["z"], size_z - EDGE_MARGIN)

        # 2. Exclusion clearance around start positions
        for f in features:
            for sx, sz in start_pts:
                dist = math.hypot(f["x"] - sx, f["z"] - sz)
                self.assertGreaterEqual(
                    dist,
                    START_EXCLUSION_RADIUS,
                    f"Feature {f['name']} at ({f['x']}, {f['z']}) inside exclusion zone of start ({sx}, {sz})",
                )

        # 3. Minimum distance between features of the same type
        by_type = {}
        for f in features:
            by_type.setdefault(f["name"], []).append(f)

        for name, feats in by_type.items():
            min_req = MIN_DIST[name]
            for i in range(len(feats)):
                for j in range(i + 1, len(feats)):
                    f1 = feats[i]
                    f2 = feats[j]
                    d = math.hypot(f1["x"] - f2["x"], f1["z"] - f2["z"])
                    self.assertGreaterEqual(
                        d,
                        min_req,
                        f"Features of type {name} too close: ({f1['x']},{f1['z']}) and ({f2['x']},{f2['z']}) d={d} < {min_req}",
                    )


# ---------------------------------------------------------------------------
# 4. Fairness
# ---------------------------------------------------------------------------


class TestMapgenFairness(MapgenBase):
    def test_each_start_gets_all_four_resources_and_exact_counts(self):
        start_pts = [(800, 800), (3200, 800), (2000, 3200)]
        starts = self._make_starts(start_pts)

        opts = self.lua.table(
            mapSizeX=4096,
            mapSizeZ=4096,
            seed=2026,
            density="normal",
            startPositions=starts,
        )
        res = _lua_to_py(self.lua, self.m.generate(opts))
        pockets = res["startPockets"]

        self.assertEqual(len(pockets), len(start_pts))

        expected_total_per_pocket = sum(EXPECTED_POCKET_COUNTS.values())  # 12 + 4 + 3 + 4 = 23

        for i, pocket in enumerate(pockets):
            self.assertEqual(pocket["x"], start_pts[i][0])
            self.assertEqual(pocket["z"], start_pts[i][1])

            p_feats = pocket["features"]
            self.assertEqual(len(p_feats), expected_total_per_pocket)

            counts = {}
            for f in p_feats:
                counts[f["name"]] = counts.get(f["name"], 0) + 1

            # All 4 resources must exist in the pocket
            for res_name, expected_count in EXPECTED_POCKET_COUNTS.items():
                self.assertIn(res_name, counts, f"Pocket {i} missing resource {res_name}")
                self.assertEqual(
                    counts[res_name],
                    expected_count,
                    f"Pocket {i} resource {res_name} count mismatch",
                )


# ---------------------------------------------------------------------------
# 5. Density
# ---------------------------------------------------------------------------


class TestMapgenDensity(MapgenBase):
    def test_sparse_less_than_normal_less_than_dense(self):
        starts = self._make_starts([(800, 800), (3200, 3200)])
        seed = 42
        size = 4096

        counts = {}
        for density in ("sparse", "normal", "dense"):
            opts = self.lua.table(
                mapSizeX=size,
                mapSizeZ=size,
                seed=seed,
                density=density,
                startPositions=starts,
            )
            res = _lua_to_py(self.lua, self.m.generate(opts))
            counts[density] = len(res["features"])

        self.assertLess(
            counts["sparse"],
            counts["normal"],
            f"Sparse ({counts['sparse']}) should be less than Normal ({counts['normal']})",
        )
        self.assertLess(
            counts["normal"],
            counts["dense"],
            f"Normal ({counts['normal']}) should be less than Dense ({counts['dense']})",
        )


# ---------------------------------------------------------------------------
# 6. Totality & Robustness
# ---------------------------------------------------------------------------


class TestMapgenTotality(MapgenBase):
    def test_nil_and_empty_opts(self):
        res1 = _lua_to_py(self.lua, self.m.generate())
        self.assertIsInstance(res1, dict)
        self.assertEqual(res1["mapSizeX"], 4096)
        self.assertEqual(res1["mapSizeZ"], 4096)
        self.assertEqual(res1["seed"], 1)
        self.assertEqual(res1["density"], "normal")
        self.assertIsInstance(res1["features"], list)
        self.assertEqual(res1["startPockets"], [])

        res2 = _lua_to_py(self.lua, self.m.generate(self.lua.table()))
        self.assertIsInstance(res2, dict)
        self.assertEqual(res2["mapSizeX"], 4096)
        self.assertEqual(res2["mapSizeZ"], 4096)
        self.assertEqual(res2["seed"], 1)

    def test_invalid_and_partial_dimensions(self):
        opts = self.lua.table(mapSizeX=-100, mapSizeZ=0)
        res = _lua_to_py(self.lua, self.m.generate(opts))
        self.assertEqual(res["mapSizeX"], 4096)
        self.assertEqual(res["mapSizeZ"], 4096)

        opts_str = self.lua.table(mapSizeX="huge", mapSizeZ=None)
        res_str = _lua_to_py(self.lua, self.m.generate(opts_str))
        self.assertEqual(res_str["mapSizeX"], 4096)
        self.assertEqual(res_str["mapSizeZ"], 4096)

    def test_invalid_density_falls_back(self):
        opts = self.lua.table(density="extreme_super_dense")
        res = _lua_to_py(self.lua, self.m.generate(opts))
        self.assertEqual(res["density"], "normal")

        opts_non_str = self.lua.table(density=123)
        res_non_str = _lua_to_py(self.lua, self.m.generate(opts_non_str))
        self.assertEqual(res_non_str["density"], "normal")

    def test_malformed_start_positions(self):
        # Mixed malformed entries in startPositions array
        starts = self.lua.table()
        starts[1] = "bad_string"
        starts[2] = self.lua.table(x=1000)  # missing z
        starts[3] = self.lua.table(z=1000)  # missing x
        starts[4] = self.lua.table(x="1000", z="2000")  # non-numbers
        starts[5] = self.lua.table(x=1500, z=1500)  # valid

        opts = self.lua.table(startPositions=starts)
        res = _lua_to_py(self.lua, self.m.generate(opts))
        self.assertEqual(len(res["startPockets"]), 1)
        self.assertEqual(res["startPockets"][0]["x"], 1500)
        self.assertEqual(res["startPockets"][0]["z"], 1500)

    def test_rng_edge_cases(self):
        # Non-numeric, negative, float, large seeds
        rng_nil = self.m.newRNG(None)
        val = rng_nil.random()
        self.assertTrue(0 <= val < 1)

        rng_str = self.m.newRNG("not_a_seed")
        self.assertTrue(0 <= rng_str.random() < 1)

        rng_neg = self.m.newRNG(-12345)
        self.assertTrue(0 <= rng_neg.random() < 1)

        rng_float = self.m.newRNG(1234.567)
        self.assertTrue(0 <= rng_float.random() < 1)

        # randomInt bounds
        r = self.m.newRNG(1)
        for _ in range(30):
            v = r.randomInt(5, 10)
            self.assertTrue(5 <= v <= 10)

        # randomChoice
        tbl = self.lua.table()
        tbl[1] = "apple"
        tbl[2] = "banana"
        chosen = r.randomChoice(tbl)
        self.assertIn(chosen, ("apple", "banana"))


# ---------------------------------------------------------------------------
# 7. Gadget Contract
# ---------------------------------------------------------------------------


class TestMapgenGadgetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assertTrue(cls, GADGET_PATH.is_file(), f"Missing gadget: {GADGET_PATH}")
        cls.src = GADGET_PATH.read_text(encoding="utf-8")

    def test_layer_is_two(self):
        self.assertIn("layer = 2,", self.src)

    def test_synced_code_guard(self):
        self.assertIn("gadgetHandler:IsSyncedCode()", self.src)

    def test_gated_on_medievalmapgen(self):
        self.assertIn("medievalmapgen", self.src)
        self.assertIn("options.medievalmapgen", self.src)

    def test_vfs_includes_pure_module(self):
        self.assertIn('VFS.Include("scripts/medieval_mapgen.lua")', self.src)

    def test_spring_feature_creation_calls(self):
        self.assertIn("Spring.CreateFeature(", self.src)
        self.assertIn("Spring.GetGroundHeight(", self.src)

    def test_game_start_callin_defined(self):
        self.assertIn("function gadget:GameStart()", self.src)

    def test_seed_resolution_modoption(self):
        self.assertIn("medievalmapgenseed", self.src)

    def test_density_resolution_modoption(self):
        self.assertIn("medievalmapdensity", self.src)

    def test_publishes_game_rules_param(self):
        self.assertIn("Spring.SetGameRulesParam(", self.src)
        self.assertIn("medieval_mapgen_features", self.src)


# ---------------------------------------------------------------------------
# 8. Modoptions
# ---------------------------------------------------------------------------


class TestMapgenModoptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lua = LuaRuntime(unpack_returned_tuples=True)
        table = lua.execute(MODOPTIONS_PATH.read_text(encoding="utf-8"))
        cls.options = {}
        for i in range(1, len(table) + 1):
            entry = table[i]
            cls.options[entry["key"]] = entry

    def test_medievalmapgen_declared(self):
        self.assertIn("medievalmapgen", self.options)
        opt = self.options["medievalmapgen"]
        self.assertEqual(opt["type"], "bool")
        self.assertFalse(opt["def"])

    def test_medievalmapgenseed_declared(self):
        self.assertIn("medievalmapgenseed", self.options)
        opt = self.options["medievalmapgenseed"]
        self.assertEqual(opt["type"], "number")
        self.assertEqual(opt["def"], 0)
        self.assertEqual(opt["min"], 0)
        self.assertEqual(opt["max"], 9999999)

    def test_medievalmapdensity_declared(self):
        self.assertIn("medievalmapdensity", self.options)
        opt = self.options["medievalmapdensity"]
        self.assertEqual(opt["type"], "list")
        self.assertEqual(opt["def"], "normal")
        items = [opt["items"][i]["key"] for i in range(1, len(opt["items"]) + 1)]
        self.assertEqual(items, ["sparse", "normal", "dense"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
