"""Headless probe runner: Phase 7 baked death-clip wiring.

Spawns one unit per articulated unitdef, kills it, and checks the evidence each
`Killed` call-in writes to infolog.txt:

    PHASE7 DEATH unit=<id> clip=death baked=1 driven=<pieces>

A PASS requires, for every articulated unitdef, that the baked `death` clip
drove at least one real model piece. A `baked=0` line means the script fell
back to its procedural tumble. Unit IDs are correlated to unitdefs through the
gadget's own spawn lines.

Mirrors run_phase5_slice6_probe.py: sync the source into the runtime SDD, run
the pinned headless engine, then harvest verdicts from infolog.txt. The engine
does not terminate on `quitforce` in this build, so a timeout is expected.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
ENGINE = ROOT / "tools" / "engine" / "recoil_2026.07.04" / "spring-headless.exe"
STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase7_death.txt"

# Every articulated unitdef. Several share a script and a baked clip set:
#   medieval_infantry.lua <- infantry, spearman, men_at_arms, king
#   medieval_archer.lua   <- archer, crossbow
#   medieval_villager.lua <- villager
#   medieval_cavalry.lua  <- cavalry, knight
UNITS = [
    "medieval_infantry",
    "medieval_spearman",
    "medieval_men_at_arms",
    "medieval_king",
    "medieval_archer",
    "medieval_crossbow",
    "medieval_villager",
    "medieval_cavalry",
    "medieval_knight",
]


def sync_source() -> None:
    dest = RUNTIME / "games" / "Medieval-BAR-TC.sdd"
    print(f"Syncing source to {dest}...")
    subprocess.run([
        "robocopy", str(ROOT), str(dest),
        "/MIR", "/XD", str(ROOT / ".git"), str(ROOT / "tools"), "/XF", ".gitignore"
    ], capture_output=True)


def run_engine() -> None:
    print(f"Launching Recoil engine: {ENGINE}...")
    cmd = [str(ENGINE), "--isolation", "--write-dir", str(RUNTIME), str(STARTSCRIPT)]
    try:
        proc = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        print(f"Engine exited {proc.returncode}")
    except subprocess.TimeoutExpired:
        print("Engine timed out after budget (expected; headless quitforce does not terminate this build)")


def parse_fields(line: str) -> dict:
    return dict(
        token.split("=", 1)
        for token in line.split()
        if "=" in token
    )


def spawn_map(text: str) -> dict:
    """Return {unitID: unitdef} from the probe gadget's spawn lines."""
    spawned = {}
    for line in text.splitlines():
        if "PHASE7 DEATH PROBE spawned" not in line:
            continue
        fields = parse_fields(line)
        if fields.get("def") and fields.get("unit"):
            spawned[fields["unit"]] = fields["def"]
    return spawned


def parse_death_lines(text: str):
    """Return {unitID: {'baked': bool, 'driven': int}} from the LUS evidence."""
    found = {}
    for line in text.splitlines():
        if "PHASE7 DEATH " not in line or "PHASE7 DEATH PROBE" in line:
            continue
        fields = parse_fields(line.split("PHASE7 DEATH ", 1)[1])
        unit = fields.get("unit")
        if not unit:
            continue
        try:
            driven = int(fields.get("driven", "0"))
        except ValueError:
            driven = 0
        entry = found.setdefault(unit, {"baked": False, "driven": 0})
        if fields.get("baked") == "1" and driven > 0:
            entry["baked"] = True
        entry["driven"] = max(entry["driven"], driven)
    return found


def main() -> int:
    sync_source()

    # Never let a previous run's verdicts leak into this one.
    infolog = RUNTIME / "infolog.txt"
    if infolog.exists():
        infolog.replace(RUNTIME / "infolog.prev.txt")

    run_engine()

    if not infolog.exists():
        print("ERROR: No infolog generated")
        return 1

    text = infolog.read_text(encoding="utf-8", errors="replace")

    print("\n--- DEATH PROBE LINES ---")
    probe_lines = [line for line in text.splitlines()
                   if "PHASE7 DEATH" in line]
    for line in probe_lines:
        print(line)
    if not probe_lines:
        print("(none)")

    found = parse_death_lines(text)
    spawned_by_id = spawn_map(text)

    print("\n--- SUMMARY ---")
    failed = []
    spawned = any("PHASE7 DEATH PROBE spawned def=" in line for line in probe_lines)
    killed = all(
        any(f"PHASE7 DEATH PROBE kill def={unit} " in line and "ok=true" in line
            for line in probe_lines)
        for unit in UNITS
    )
    complete = any("PHASE7 DEATH PROBE complete" in line for line in probe_lines)
    for unit in UNITS:
        unit_ids = [uid for uid, name in spawned_by_id.items() if name == unit]
        entries = [found[uid] for uid in unit_ids if uid in found]
        baked = [entry for entry in entries if entry["baked"]]
        if baked:
            print(f"{unit}: PASS (baked death clip, driven={baked[0]['driven']})")
        elif entries:
            print(f"{unit}: FAIL (baked=0, procedural fallback)")
            failed.append(unit)
        else:
            print(f"{unit}: FAIL (no PHASE7 DEATH line for its unit id)")
            failed.append(unit)

    print(f"spawn: {'PASS' if spawned else 'FAIL'}")
    print(f"kill: {'PASS' if killed else 'FAIL'}")
    print(f"complete: {'PASS' if complete else 'FAIL'}")
    if not spawned or not killed or not complete:
        failed.append("probe-lifecycle")

    if not failed:
        print("PHASE7 DEATH PROBE: ALL VERDICTS PASSED")
        return 0
    print(f"PHASE7 DEATH PROBE: FAILED ({', '.join(failed)})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
