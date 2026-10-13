"""Phase 7 Slice 3 tests: full static model & texture coverage.

Validates that:

1. `tools/assets/convert_0ad.py` declares a dedicated source model for every
   building in the medieval roster plus the Villager, Spearman and King, and that
   the declaration is wired into the conversion loop.
2. `tools/assets/0ad-manifest.json` tracks every converted model with complete,
   self-consistent metadata: actor/mesh/texture provenance, an OBJ path, a tex1
   binding, geometry counts and post-scale bounds, with the source entries hashed.
3. Every dedicated OBJ exists on disk in `objects3d/0ad/` with real geometry
   (vertex/face counts matching the manifest, one-based in-range face indices)
   and a sibling `objects3d/0ad/<name>.lua` texture lookup that resolves to an
   on-disk, well-formed DDS in `unittextures/0ad/`.
4. No two dedicated models share a source mesh, i.e. the placeholder recycling
   that Slice 3 removes cannot silently return.
5. Every `units/*.lua` def has an `objectName` that resolves to an existing
   `objects3d/` file, and the building defs plus Villager/Spearman/King point at
   their own dedicated OBJ rather than a borrowed one.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
import unittest

from lupa import LuaRuntime

from tools.assets.convert_0ad import BUILDINGS, MODELS, UNITS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "tools/assets/0ad-manifest.json"
OBJECTS_DIR = ROOT / "objects3d/0ad"
TEXTURES_DIR = ROOT / "unittextures/0ad"
UNITS_DIR = ROOT / "units"

# The three infantry variants that previously recycled a shared body.
DEDICATED_UNITS = {
    "medieval_villager": "art/actors/units/britons/citizen_male.xml",
    "medieval_spearman": "art/actors/units/britons/infantry_spearman_a.xml",
    "medieval_king": "art/actors/units/britons/hero_infantry_swordsman_cunobelin.xml",
}

# The eleven buildings that previously rendered as a recycled infantry body.
DEDICATED_BUILDINGS = {
    "medieval_town_center": "art/actors/structures/britons/civic_centre.xml",
    "medieval_house": "art/actors/structures/britons/house.xml",
    "medieval_barracks": "art/actors/structures/britons/barracks.xml",
    "medieval_stables": "art/actors/structures/britons/stable.xml",
    "medieval_granary": "art/actors/structures/britons/farmstead.xml",
    "medieval_lumber_camp": "art/actors/structures/britons/storehouse.xml",
    "medieval_market": "art/actors/structures/britons/market.xml",
    "medieval_blacksmith": "art/actors/structures/britons/blacksmith.xml",
    "medieval_fletcher": "art/actors/structures/britons/range.xml",
    "medieval_tower": "art/actors/structures/britons/scout_tower.xml",
    "medieval_wall": "art/actors/structures/britons/wall_medium.xml",
}

DEDICATED = {**DEDICATED_UNITS, **DEDICATED_BUILDINGS}

# Metadata every manifest model entry must carry.
REQUIRED_ENTRY_KEYS = (
    "actor", "mesh", "texture", "obj", "tex1",
    "vertices", "faces", "bones_ignored", "props_ignored", "bounds",
)

# Units stay human-scaled (~3.85 model units tall, x8); buildings are structural.
UNIT_HEIGHT_RANGE = (25.0, 40.0)
MIN_BUILDING_HEIGHT = 30.0
MAX_MODEL_SPAN = 400.0
MIN_FACES = 500


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_unit_defs() -> dict[str, dict]:
    """Parse every units/*.lua into {defname: def} using a fresh Lua runtime."""
    defs: dict[str, dict] = {}
    for path in sorted(UNITS_DIR.glob("*.lua")):
        lua = LuaRuntime(unpack_returned_tuples=True)
        table = lua.execute(path.read_text(encoding="utf-8"))
        for name, body in table.items():
            defs[name] = {
                "file": path,
                "objectName": body["objectName"],
                "script": body["script"],
            }
    return defs


def read_obj_stats(path: Path) -> dict:
    """Count OBJ vertices/faces and check every face index is in range."""
    vertices = 0
    faces = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            vertices += 1
        elif line.startswith("f "):
            faces += 1
            for ref in line.split()[1:]:
                index = int(ref.split("/")[0])
                if index < 1 or index > vertices:
                    raise AssertionError(f"{path.name}: face index {index} out of range")
    return {"vertices": vertices, "faces": faces}


def read_dds_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) from a DDS header, validating the signature."""
    data = path.read_bytes()
    if data[:4] != b"DDS ":
        raise AssertionError(f"{path} is not a DDS file")
    height, width = struct.unpack_from("<II", data, 12)
    return width, height


class TestConverterSources(unittest.TestCase):
    """The converter must declare a dedicated source for every covered model."""

    def test_buildings_table_covers_the_whole_roster(self):
        self.assertEqual(set(BUILDINGS), set(DEDICATED_BUILDINGS))

    def test_new_units_are_declared(self):
        for name in DEDICATED_UNITS:
            self.assertIn(name, UNITS)

    def test_every_declared_model_names_actor_mesh_and_texture(self):
        for name, choice in MODELS.items():
            with self.subTest(model=name):
                for key in ("actor", "mesh", "texture"):
                    self.assertIn(key, choice)
                    self.assertTrue(choice[key])

    def test_declared_actors_match_the_dedicated_mapping(self):
        for name, actor in DEDICATED.items():
            with self.subTest(model=name):
                self.assertEqual(MODELS[name]["actor"], actor)

    def test_models_union_covers_units_and_buildings(self):
        self.assertEqual(set(MODELS), set(UNITS) | set(BUILDINGS))

    def test_no_two_dedicated_models_share_a_source_mesh(self):
        meshes = {name: MODELS[name]["mesh"] for name in DEDICATED}
        self.assertEqual(len(set(meshes.values())), len(meshes),
                         f"duplicate source meshes: {meshes}")


class TestManifest(unittest.TestCase):
    """The manifest must track every converted model with valid metadata."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()

    def test_license_and_transform_provenance(self):
        self.assertTrue(self.manifest["license"].startswith("CC-BY-SA-3.0"))
        self.assertEqual(self.manifest["source"], "0 A.D. alpha 28 public.zip")
        self.assertEqual(self.manifest["transform"]["axes"], "Y-up unchanged")
        self.assertGreater(self.manifest["transform"]["scale"], 0)

    def test_manifest_tracks_every_converted_model(self):
        tracked = set(self.manifest["units"]) | set(self.manifest["buildings"])
        self.assertEqual(tracked, set(MODELS))

    def test_buildings_group_covers_the_whole_roster(self):
        self.assertEqual(set(self.manifest["buildings"]), set(DEDICATED_BUILDINGS))

    def test_dedicated_units_are_tracked(self):
        for name in DEDICATED_UNITS:
            self.assertIn(name, self.manifest["units"])

    def test_every_entry_carries_the_required_metadata(self):
        for group in ("units", "buildings"):
            for name, entry in self.manifest[group].items():
                with self.subTest(model=name):
                    for key in REQUIRED_ENTRY_KEYS:
                        self.assertIn(key, entry)
                    self.assertEqual(entry["obj"], f"objects3d/0ad/{name}.obj")
                    self.assertEqual(entry["tex1"], f"0ad/{name}.dds")
                    self.assertIsInstance(entry["vertices"], int)
                    self.assertIsInstance(entry["faces"], int)
                    self.assertGreater(entry["vertices"], 0)
                    self.assertGreaterEqual(entry["faces"], MIN_FACES)
                    self.assertGreaterEqual(entry["bones_ignored"], 0)
                    self.assertGreaterEqual(entry["props_ignored"], 0)

    def test_bounds_are_well_formed(self):
        for group in ("units", "buildings"):
            for name, entry in self.manifest[group].items():
                with self.subTest(model=name):
                    bounds = entry["bounds"]
                    self.assertEqual(set(bounds), {"x", "y", "z"})
                    for axis, (low, high) in bounds.items():
                        self.assertLess(low, high, f"{name}.{axis}")
                        self.assertLessEqual(high - low, MAX_MODEL_SPAN, f"{name}.{axis}")

    def test_unit_models_are_human_scaled(self):
        for name in DEDICATED_UNITS:
            with self.subTest(model=name):
                low, high = self.manifest["units"][name]["bounds"]["y"]
                self.assertGreaterEqual(low, 0.0)
                self.assertTrue(UNIT_HEIGHT_RANGE[0] <= high <= UNIT_HEIGHT_RANGE[1],
                                f"{name} height {high} outside {UNIT_HEIGHT_RANGE}")

    def test_building_models_are_structure_scaled(self):
        for name in DEDICATED_BUILDINGS:
            with self.subTest(model=name):
                height = self.manifest["buildings"][name]["bounds"]["y"]
                self.assertGreaterEqual(height[1], MIN_BUILDING_HEIGHT)

    def test_source_entries_are_hashed(self):
        entries = self.manifest["entries"]
        for group in ("units", "buildings"):
            for name, entry in self.manifest[group].items():
                for key in ("actor", "mesh", "texture"):
                    with self.subTest(model=name, entry=entry[key]):
                        self.assertIn(entry[key], entries)
                        recorded = entries[entry[key]]
                        self.assertEqual(len(recorded["sha256"]), 64)
                        self.assertGreater(recorded["bytes"], 0)

    def test_actor_paths_are_authentic_0ad_sources(self):
        for group, mapping in (("units", DEDICATED_UNITS), ("buildings", DEDICATED_BUILDINGS)):
            for name, actor in mapping.items():
                with self.subTest(model=name):
                    self.assertEqual(self.manifest[group][name]["actor"], actor)

    def test_dedicated_models_use_distinct_source_meshes(self):
        meshes = [self.manifest["units"][n]["mesh"] for n in DEDICATED_UNITS]
        meshes += [self.manifest["buildings"][n]["mesh"] for n in DEDICATED_BUILDINGS]
        self.assertEqual(len(set(meshes)), len(meshes), "a source mesh is still recycled")


class TestDedicatedAssetsOnDisk(unittest.TestCase):
    """Dedicated OBJ, Lua lookup and DDS must exist and be valid."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = load_manifest()

    def _entry(self, name: str) -> dict:
        for group in ("units", "buildings"):
            if name in self.manifest[group]:
                return self.manifest[group][name]
        raise AssertionError(f"{name} missing from the manifest")

    def test_obj_lua_and_dds_exist(self):
        for name in DEDICATED:
            with self.subTest(model=name):
                self.assertTrue((OBJECTS_DIR / f"{name}.obj").is_file())
                self.assertTrue((OBJECTS_DIR / f"{name}.lua").is_file())
                self.assertTrue((TEXTURES_DIR / f"{name}.dds").is_file())

    def test_obj_geometry_matches_the_manifest(self):
        for name in DEDICATED:
            with self.subTest(model=name):
                stats = read_obj_stats(OBJECTS_DIR / f"{name}.obj")
                entry = self._entry(name)
                self.assertEqual(stats["vertices"], entry["vertices"])
                self.assertEqual(stats["faces"], entry["faces"])

    def test_obj_carries_the_expected_structure(self):
        for name in DEDICATED:
            with self.subTest(model=name):
                text = (OBJECTS_DIR / f"{name}.obj").read_text(encoding="utf-8")
                if name in DEDICATED_BUILDINGS:
                    self.assertIn("o base", text)
                    self.assertIn("usemtl base", text)
                else:
                    # Articulated units split into per-bone `o <name>` pieces
                    # instead of one merged `o base` root object.
                    pieces = [
                        line.split(None, 1)[1].strip()
                        for line in text.splitlines()
                        if line.startswith("o ")
                    ]
                    self.assertTrue(
                        pieces, "unit OBJ must define at least one 'o <name>' piece"
                    )
                # `g base` would make Assimp duplicate the mesh (base + base00);
                # the converter must not emit a group line.
                self.assertNotIn("g base", text)
                self.assertIn("vt ", text)
                self.assertIn("vn ", text)

    def test_texture_lookup_lua_resolves_to_the_dds(self):
        for name in DEDICATED:
            with self.subTest(model=name):
                lua = LuaRuntime(unpack_returned_tuples=True)
                table = lua.execute((OBJECTS_DIR / f"{name}.lua").read_text(encoding="utf-8"))
                self.assertEqual(table["tex1"], f"0ad/{name}.dds")
                self.assertTrue((TEXTURES_DIR / f"{name}.dds").is_file())

    def test_textures_are_valid_dds_with_usable_dimensions(self):
        for name in DEDICATED:
            with self.subTest(model=name):
                path = TEXTURES_DIR / f"{name}.dds"
                self.assertGreater(path.stat().st_size, 1024)
                width, height = read_dds_dimensions(path)
                self.assertGreater(width, 0)
                self.assertGreater(height, 0)

    def test_texture_digest_is_recorded_for_the_source_dds(self):
        # The manifest hashes the archive entry, not the copy; confirm the copy is
        # byte-identical to the recorded length so the two cannot silently diverge.
        for name in DEDICATED:
            with self.subTest(model=name):
                entry = self._entry(name)
                recorded = self.manifest["entries"][entry["texture"]]
                on_disk = (TEXTURES_DIR / f"{name}.dds").read_bytes()
                self.assertEqual(len(on_disk), recorded["bytes"])
                self.assertEqual(hashlib.sha256(on_disk).hexdigest(), recorded["sha256"])


class TestUnitDefBindings(unittest.TestCase):
    """units/*.lua must point at real, dedicated objects3d files."""

    @classmethod
    def setUpClass(cls):
        cls.defs = load_unit_defs()

    def test_roster_is_non_empty(self):
        self.assertGreaterEqual(len(self.defs), 20)

    def test_every_object_name_resolves_to_a_real_file(self):
        for name, definition in self.defs.items():
            with self.subTest(unit=name):
                object_name = definition["objectName"]
                self.assertTrue(object_name.endswith(".obj"), object_name)
                self.assertTrue((ROOT / "objects3d" / object_name).is_file(),
                                f"{name} -> {object_name} missing")

    def test_no_def_references_the_placeholder(self):
        for name, definition in self.defs.items():
            with self.subTest(unit=name):
                self.assertNotIn("placeholder", definition["objectName"])

    def test_buildings_point_at_their_own_dedicated_model(self):
        for name in DEDICATED_BUILDINGS:
            with self.subTest(unit=name):
                self.assertEqual(self.defs[name]["objectName"], f"0ad/{name}.obj")

    def test_villager_spearman_and_king_have_dedicated_models(self):
        for name in DEDICATED_UNITS:
            with self.subTest(unit=name):
                self.assertEqual(self.defs[name]["objectName"], f"0ad/{name}.obj")

    def test_no_unit_recycles_another_units_dedicated_mesh(self):
        dedicated = {f"0ad/{name}.obj" for name in DEDICATED}
        owners: dict[str, list[str]] = {}
        for name, definition in self.defs.items():
            object_name = definition["objectName"]
            if object_name in dedicated:
                owners.setdefault(object_name, []).append(name)
        for object_name, users in owners.items():
            with self.subTest(object_name=object_name):
                self.assertEqual(users, [object_name.removeprefix("0ad/").removesuffix(".obj")],
                                 f"{object_name} recycled by {users}")

    def test_lua_unit_scripts_are_not_repointed_by_this_slice(self):
        # Slice 3 is asset coverage only; the shared LUS bindings stay valid.
        # Buildings declare no `script` field, so only mobile units are checked.
        checked = 0
        for name, definition in self.defs.items():
            script = definition["script"]
            if script is None:
                continue
            checked += 1
            with self.subTest(unit=name):
                self.assertTrue((ROOT / "scripts" / script).is_file(),
                                f"{name} -> {script} missing")
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
