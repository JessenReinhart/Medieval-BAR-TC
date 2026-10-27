"""Extract selected 0 A.D. audio assets (.ogg) for Medieval-BAR-TC.

Source archive: 0 A.D. alpha 28 public.zip.
Audio license: CC-BY-SA-3.0 (Wildfire Games).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import zipfile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARCHIVE = Path(
    os.environ.get("ZEROAD_ARCHIVE")
    or os.environ.get("0AD_ARCHIVE_PATH")
    or (Path.home() / "AppData/Local/0 A.D. Empires Ascendant/binaries/data/mods/public/public.zip")
)

# Map target relative destination -> source zip path
SOUND_MAP = {
    # Weapons / Combat
    "sounds/weapons/sword_swing.ogg": "audio/attack/weapon/sword_attack_01.ogg",
    "sounds/weapons/sword_hit.ogg": "audio/attack/impact/fleshstab_01.ogg",
    "sounds/weapons/spear_thrust.ogg": "audio/attack/weapon/pike_attack_01.ogg",
    "sounds/weapons/spear_hit.ogg": "audio/attack/impact/shield_metal_01.ogg",
    "sounds/weapons/bow_shoot.ogg": "audio/attack/weapon/bow_attack_01.ogg",
    "sounds/weapons/arrow_hit.ogg": "audio/attack/impact/arrow_01.ogg",
    "sounds/weapons/crossbow_shoot.ogg": "audio/attack/weapon/bow_attack_03.ogg",
    "sounds/weapons/bolt_hit.ogg": "audio/attack/impact/arrow_metal_01.ogg",
    "sounds/weapons/lance_charge.ogg": "audio/attack/weapon/sword_attack_03.ogg",
    "sounds/weapons/lance_hit.ogg": "audio/attack/impact/fleshimp_10.ogg",
    "sounds/weapons/catapult_shoot.ogg": "audio/attack/siege/ballist_attack_01.ogg",
    "sounds/weapons/catapult_hit.ogg": "audio/attack/impact/siegeprojectilehit_01.ogg",
    "sounds/weapons/dagger_hit.ogg": "audio/attack/impact/fleshstab_02.ogg",
    # Economy & Gathering
    "sounds/economy/wood_chop.ogg": "audio/resource/lumbering/lumber_tree_01.ogg",
    "sounds/economy/stone_mine.ogg": "audio/resource/mining/mine_metal_01.ogg",
    "sounds/economy/construction.ogg": "audio/resource/construction/con_saw_01.ogg",
    "sounds/economy/haul_cart.ogg": "audio/actor/human/movement/Footsteps/Footstep_Gravel_Walking.ogg",
    # Interface & Alerts
    "sounds/ui/alarm_under_attack.ogg": "audio/interface/alarm/alarmattackcity_1.ogg",
    "sounds/ui/building_complete.ogg": "audio/interface/complete/building/complete_civ_center.ogg",
    "sounds/ui/unit_select.ogg": "audio/interface/ui/gamesetup_join.ogg",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_sounds(
    archive: Path = DEFAULT_ARCHIVE, root: Path = ROOT
) -> dict:
    if not archive.exists():
        raise FileNotFoundError(f"0 A.D. archive not found: {archive}")

    manifest: dict = {
        "source": "0 A.D. alpha 28 public.zip",
        "archive": "mods/public/public.zip",
        "license": "CC-BY-SA-3.0 (Wildfire Games)",
        "sounds": {},
    }

    with zipfile.ZipFile(archive, "r") as zf:
        namelist = set(zf.namelist())
        for rel_dest, src_path in SOUND_MAP.items():
            if src_path not in namelist:
                raise KeyError(f"Missing audio entry in archive: {src_path}")

            data = zf.read(src_path)
            digest = sha256_bytes(data)

            dest_file = root / rel_dest
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_bytes(data)

            manifest["sounds"][rel_dest] = {
                "source": src_path,
                "bytes": len(data),
                "sha256": digest,
            }

    manifest_path = root / "tools/assets/0ad-sound-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        default=DEFAULT_ARCHIVE,
        help="Path to 0 A.D. public.zip",
    )
    args = parser.parse_args()
    manifest = extract_sounds(archive=args.archive)
    print(
        f"Extracted {len(manifest['sounds'])} sound files to {ROOT / 'sounds'}."
    )


if __name__ == "__main__":
    main()
