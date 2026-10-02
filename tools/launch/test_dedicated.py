import os
import re
import shutil
import subprocess

ROOT = r'C:\tmp\bar-tc-repo'
ENGINE = os.path.join(ROOT, 'tools', 'engine', 'recoil_2026.07.04', 'spring-dedicated.exe')
RUNTIME = os.path.join(ROOT, 'tools', 'runtime-dedicated-test')

if os.path.exists(RUNTIME):
    shutil.rmtree(RUNTIME)
os.makedirs(os.path.join(RUNTIME, 'maps'), exist_ok=True)
game = os.path.join(RUNTIME, 'games', 'Medieval-BAR-TC.sdd')
shutil.copytree(ROOT, game, ignore=shutil.ignore_patterns('.git', 'tools', '.pytest_cache', '__pycache__'))
shutil.copy(os.path.join(ROOT, 'tools', 'runtime', 'maps', 'quicksilver_remake_1.24.sd7'), os.path.join(RUNTIME, 'maps'))
script = os.path.join(RUNTIME, 'startscript.txt')
shutil.copy(os.path.join(ROOT, 'tools', 'launch', 'startscript.txt'), script)

# Dedicated uses isolation-dir; it does not support the headless binary's --write-dir.
proc = subprocess.Popen([ENGINE, '--isolation', '--isolation-dir', RUNTIME, script],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        cwd=ROOT)
try:
    proc.wait(timeout=15)
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
phase_lines = [l for l in log.splitlines() if 'Phase 1:' in l]
print('dedicated-exit-code=', proc.returncode)
print('dedicated-max-frame=', max(frames) if frames else None)
print('dedicated-num-frame-logs=', len(frames))
print('dedicated-phase-lines=', phase_lines)
print('dedicated-log-tail=')
print('\n'.join(log.splitlines()[-20:]))
