import os
import re
import shutil
import subprocess
import time

ROOT = r'C:\tmp\bar-tc-repo'
ENGINE = os.path.join(ROOT, 'tools', 'engine', 'recoil_2026.07.04', 'spring-headless.exe')
BASE = open(os.path.join(ROOT, 'tools', 'launch', 'startscript.txt'), encoding='utf-8').read()
variants = {
    'ready': BASE.replace('Spectator=0;', 'Spectator=0;\n\t\tReady=1;'),
    'ready_startpos': BASE.replace('Spectator=0;', 'Spectator=0;\n\t\tReady=1;\n\t\tStartPosReady=1;'),
    'host_ready': BASE.replace('Spectator=0;', 'Spectator=0;\n\t\tReady=1;\n\t\tHost=1;'),
    'ready_ai_isfromdemo': BASE.replace('Spectator=0;', 'Spectator=0;\n\t\tReady=1;\n\t\treadyToStart=1;'),
}
for name, script in variants.items():
    runtime = os.path.join(ROOT, 'tools', 'runtime-variant-' + name)
    if os.path.exists(runtime): shutil.rmtree(runtime)
    os.makedirs(os.path.join(runtime, 'maps'), exist_ok=True)
    game = os.path.join(runtime, 'games', 'Medieval-BAR-TC.sdd')
    shutil.copytree(ROOT, game, ignore=shutil.ignore_patterns('.git', 'tools', '.pytest_cache', '__pycache__'))
    shutil.copy(os.path.join(ROOT, 'tools', 'runtime', 'maps', 'quicksilver_remake_1.24.sd7'), os.path.join(runtime, 'maps'))
    script_path = os.path.join(runtime, 'startscript.txt')
    open(script_path, 'w', encoding='utf-8').write(script)
    proc = subprocess.Popen([ENGINE, '--isolation', '--write-dir', runtime, script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    if proc.poll() is None:
        proc.terminate()
        try: proc.wait(3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
    log = open(os.path.join(runtime, 'infolog.txt'), encoding='utf-8', errors='ignore').read() if os.path.exists(os.path.join(runtime, 'infolog.txt')) else ''
    frames = re.findall(r'\[f=(-?\d+)\]', log)
    phases = [line for line in log.splitlines() if 'Phase 1:' in line]
    print(name, 'max-frame=', max(map(int, frames)) if frames else 'none', 'phase=', phases[-3:])
    print('  tail=', log.splitlines()[-1:] if log else 'no-log')
