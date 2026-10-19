"""Headless probe runner: Phase 7 death-clip wiring, both modes.

Mode 1 (`baked`): spawns one unit per articulated unitdef, kills it, and checks
the evidence each `Killed` call-in writes to infolog.txt:

    PHASE7 DEATH unit=<id> clip=death baked=1 driven=<pieces>

Mode 2 (`procedural`): same probe with `medievalanimfallback=1`, which makes the
gadget set `medieval_force_procedural_death` on each unit. The LUS must then skip
the bake and emit `clip=procedural baked=0`, proving the fallback still works.

A mode PASSES when every articulated unitdef produces its expected evidence.
Unit IDs are correlated to unitdefs through the gadget's own spawn lines.

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

BAKED_STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase7_death.txt"
FALLBACK_STARTSCRIPT = ROOT / "tools" / "launch" / "startscript_phase7_death_fallback.txt"

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

# (label echoed by the gadget, startscript, expect baked clip)
MODES = [
    ("baked", BAKED_STARTSCRIPT, True),
    ("procedural", FALLBACK_STARTSCRIPT, False),
]


def sync_source() -> None:
    dest = RUNTIME / "games" / "Medieval-BAR-TC.sdd"
    print(f"Syncing source to {dest}...")
    subprocess.run([
        "robocopy", str(ROOT), str(dest),
        "/MIR", "/XD", str(ROOT / ".git"), str(ROOT / "tools"), "/XF", ".gitignore"
    ], capture_output=True)


def run_engine(label: str, startscript: Path) -> Path:
    infolog = RUNTIME / "infolog.txt"
    if infolog.exists():
        infolog.replace(RUNTIME / f"infolog.prev-{label}.txt")

    print(f"\n[{label}] Launching Recoil engine: {ENGINE}...")
    cmd = [str(ENGINE), "--isolation", "--write-dir", str(RUNTIME), str(startscript)]
    try:
        proc = subprocess.run(cmd, timeout=90, capture_output=True, text=True)
        print(f"[{label}] Engine exited {proc.returncode}")
    except subprocess.TimeoutExpired:
        print(f"[{label}] Engine timed out after budget (expected; headless quitforce does not terminate this build)")
    return infolog


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
    """Return {unitID: {'baked': bool, 'procedural': bool, 'driven': int}}."""
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
        entry = found.setdefault(unit, {"baked": False, "procedural": False, "driven": 0})
        if fields.get("baked") == "1" and driven > 0:
            entry["baked"] = True
        if fields.get("baked") == "0":
            entry["procedural"] = True
        entry["driven"] = max(entry["driven"], driven)
    return found


def check_mode(label: str, expect_baked: bool, text: str) -> list[str]:
    probe_lines = [line for line in text.splitlines() if "PHASE7 DEATH" in line]

    print(f"\n--- [{label}] DEATH PROBE LINES ---")
    for line in probe_lines:
        print(line)
    if not probe_lines:
        print("(none)")

    failures = []
    found = parse_death_lines(text)
    spawned_by_id = spawn_map(text)

    print(f"\n--- [{label}] SUMMARY ---")
    spawn_line = next(
        (line for line in probe_lines
         if "PHASE7 DEATH PROBE spawn-summary" in line and f"mode={label}" in line),
        None,
    )
    spawned = spawn_line is not None and f"spawned={len(UNITS)}" in spawn_line
    killed = all(
        any(f"PHASE7 DEATH PROBE kill def={unit} " in line and "ok=true" in line
            for line in probe_lines)
        for unit in UNITS
    )
    complete = any("PHASE7 DEATH PROBE complete" in line for line in probe_lines)

    for unit in UNITS:
        unit_ids = [uid for uid, name in spawned_by_id.items() if name == unit]
        entries = [found[uid] for uid in unit_ids if uid in found]
        if expect_baked:
            baked = [entry for entry in entries if entry["baked"]]
            if baked:
                print(f"{unit}: PASS (baked death clip, driven={baked[0]['driven']})")
            else:
                print(f"{unit}: FAIL (no baked death clip)")
                failures.append(unit)
        else:
            procedural = [entry for entry in entries if entry["procedural"]]
            if procedural and not any(entry["baked"] for entry in entries):
                print(f"{unit}: PASS (procedural fallback, baked=0)")
            else:
                print(f"{unit}: FAIL (baked clip still played, or no baked=0 line)")
                failures.append(unit)

    print(f"mode: {'PASS' if spawned else 'FAIL'}")
    print(f"spawn: {'PASS' if spawned else 'FAIL'}")
    print(f"kill: {'PASS' if killed else 'FAIL'}")
    print(f"complete: {'PASS' if complete else 'FAIL'}")
    if not spawned or not killed or not complete:
        failures.append("probe-lifecycle")
    return failures


def main() -> int:
    sync_source()

    all_failed = {}
    for label, startscript, expect_baked in MODES:
        infolog = run_engine(label, startscript)
        if not infolog.exists():
            print(f"[{label}] ERROR: No infolog generated")
            all_failed[label] = ["infolog"]
            continue
        text = infolog.read_text(encoding="utf-8", errors="replace")
        all_failed[label] = check_mode(label, expect_baked, text)

    print("\n=== OVERALL ===")
    failed = False
    for label, _, _ in MODES:
        problems = all_failed.get(label) or []
        if problems:
            failed = True
            print(f"{label}: FAILED ({', '.join(problems)})")
        else:
            print(f"{label}: PASSED")

    if not failed:
        print("PHASE7 DEATH PROBE: ALL MODES PASSED")
        return 0
    print("PHASE7 DEATH PROBE: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
