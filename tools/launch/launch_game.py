"""Launch Medieval-BAR-TC in windowed or headless mode.

Synchronizes the repository sources to tools/runtime/games/Medieval-BAR-TC.sdd,
sets up the startscript and map, and executes the Recoil engine.

Usage:
    python tools/launch/launch_game.py              # Windowed interactive game
    python tools/launch/launch_game.py --headless   # Headless simulation
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tools" / "runtime"
GAME_SDD = RUNTIME / "games" / "Medieval-BAR-TC.sdd"
MAP_SRC = RUNTIME / "maps" / "quicksilver_remake_1.24.sd7"


def sync_sdd() -> None:
    print(f"Syncing game sources to {GAME_SDD}...")
    GAME_SDD.mkdir(parents=True, exist_ok=True)
    cmd = [
        "robocopy",
        str(ROOT),
        str(GAME_SDD),
        "/MIR",
        "/XD",
        str(ROOT / ".git"),
        str(ROOT / "tools"),
        "tests",
        "docs",
        "__pycache__",
        ".pytest_cache",
        ".benchmarks",
        ".freebuff",
        "/XF",
        ".gitignore",
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode >= 8:
        raise RuntimeError(f"robocopy failed with exit code {proc.returncode}")


sync_game_to_runtime = sync_sdd


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch Medieval-BAR-TC")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless instead of windowed GUI",
    )
    parser.add_argument(
        "--engine",
        type=Path,
        default=None,
        help="Path to spring.exe / spring-headless.exe",
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=ROOT / "tools" / "launch" / "startscript_play.txt",
        help="Path to custom startscript",
    )
    args = parser.parse_args()

    sync_sdd()

    if args.engine:
        engine_exe = args.engine
    else:
        exe_name = "spring-headless.exe" if args.headless else "spring.exe"
        engine_exe = ROOT / "tools" / "engine" / "recoil_2026.07.04" / exe_name

    if not engine_exe.exists():
        print(f"Error: Engine binary not found at {engine_exe}", file=sys.stderr)
        return 1

    script_target = RUNTIME / "script.txt"
    script_target.write_text(args.script.read_text(encoding="utf-8"), encoding="utf-8")

    launch_cmd = [str(engine_exe), "--write-dir", str(RUNTIME), str(script_target)]
    if args.headless:
        launch_cmd.insert(1, "--isolation")

    print(f"Launching engine: {' '.join(launch_cmd)}")
    if args.headless:
        proc = subprocess.run(launch_cmd)
        return proc.returncode
    else:
        # Launch detached/windowed
        subprocess.Popen(launch_cmd)
        print("Engine process started.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
