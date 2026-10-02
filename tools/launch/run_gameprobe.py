import os
import re
import shutil
import subprocess
import sys
import time

ROOT = r'C:\tmp\bar-tc-repo'
ENGINE = os.path.join(ROOT, 'tools', 'engine', 'recoil_2026.07.04', 'spring-headless.exe')
RUNTIME = os.path.join(ROOT, 'tools', 'runtime-gameprobe')
TIMEOUT = int(sys.argv[1]) if len(sys.argv) > 1 else 20

if os.path.exists(RUNTIME):
    shutil.rmtree(RUNTIME)
os.makedirs(os.path.join(RUNTIME, 'maps'), exist_ok=True)
game = os.path.join(RUNTIME, 'games', 'Medieval-BAR-TC.sdd')
shutil.copytree(ROOT, game, ignore=shutil.ignore_patterns('.git', 'tools', '.pytest_cache', '__pycache__'))
shutil.copy(os.path.join(ROOT, 'tools', 'runtime', 'maps', 'quicksilver_remake_1.24.sd7'), os.path.join(RUNTIME, 'maps'))
script = os.path.join(RUNTIME, 'startscript.txt')
shutil.copy(os.path.join(ROOT, 'tools', 'launch', 'startscript.txt'), script)

proc = subprocess.Popen([ENGINE, '--isolation', '--write-dir', RUNTIME, script],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    proc.wait(timeout=TIMEOUT)
except subprocess.TimeoutExpired:
    proc.terminate()
    try:
        proc.wait(3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

log_path = os.path.join(RUNTIME, 'infolog.txt')
log = ''
if os.path.exists(log_path):
    with open(log_path, encoding='utf-8', errors='ignore') as f:
        log = f.read()

frames = [int(x) for x in re.findall(r'\[f=(-?\d+)\]', log)]
max_frame = max(frames) if frames else None
phase_lines = [l for l in log.splitlines() if 'Phase 1:' in l]
print('exit-code=', proc.returncode)
print('max-frame=', max_frame)
print('num-frame-logs=', len(frames))
print('phase-lines-count=', len(phase_lines))
for l in phase_lines[-10:]:
    print('  ', l)
# Tail of log after loading
print('--- tail ---')
print('\n'.join(log.splitlines()[-25:]))