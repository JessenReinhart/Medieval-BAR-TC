import socket
import subprocess
import time
import os
import shutil

rt = 'tools/runtime-autohost-probe'
os.makedirs(rt, exist_ok=True)
os.makedirs(os.path.join(rt, 'maps'), exist_ok=True)
with open(os.path.join(rt, 'springsettings.cfg'), 'w', encoding='utf-8') as f:
    f.write('LogSections=AutohostInterface,GameServer,Net\n')

script = """[GAME]
{
\tMapName=Quicksilver Remake 1.24;
\tGameType=Medieval BAR Total Conversion 0.1.0-phase1;
\tStartPosType=1;
\tGameStartDelay=0;
\tIsHost=1;
\tAutohostPort=8453;
\tMyPlayerName=HeadlessChecker;
\tRecordDemo=0;
\t[ALLYTEAM0]
\t{
\t\tNumAllies=0;
\t}
\t[ALLYTEAM1]
\t{
\t\tNumAllies=0;
\t}
\t[TEAM0]
\t{
\t\tTeamLeader=0;
\t\tAllyTeam=0;
\t\tStartPosX=1800;
\t\tStartPosZ=2400;
\t}
\t[TEAM1]
\t{
\t\tTeamLeader=0;
\t\tAllyTeam=1;
\t\tStartPosX=4200;
\t\tStartPosZ=2400;
\t}
\t[PLAYER0]
\t{
\t\tName=HeadlessChecker;
\t\tTeam=0;
\t\tSpectator=0;
\t}
\t[AI0]
\t{
\t\tName=BotOpponent;
\t\tShortName=NullAI;
\t\tTeam=1;
\t\tHost=0;
\t}
\t[MODOPTIONS]
\t{
\t\tdeathmode=neverend;
\t\tmedievaltest=1;
\t\tmedievaltestcount=200;
\t}
}
"""
script_path = os.path.join(rt, 'startscript.txt')
with open(script_path, 'w', encoding='utf-8') as f:
    f.write(script)

src_root = r'C:\tmp\bar-tc-repo'
game_dir = os.path.join(rt, 'games', 'Medieval-BAR-TC.sdd')
if os.path.exists(game_dir):
    shutil.rmtree(game_dir)
shutil.copytree(src_root, game_dir, ignore=shutil.ignore_patterns('.git', 'tools', '.pytest_cache', '__pycache__'))
os.makedirs(os.path.join(rt, 'maps'), exist_ok=True)
shutil.copy(r'C:\tmp\bar-tc-repo\tools\runtime\maps\quicksilver_remake_1.24.sd7', os.path.join(rt, 'maps'))

infolog = os.path.join(rt, 'infolog.txt')
if os.path.exists(infolog):
    os.remove(infolog)

engine = 'tools/engine/recoil_2026.07.04/spring-headless.exe'
proc = subprocess.Popen([engine, '--isolation', '--write-dir', rt, script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print('Spawned engine pid:', proc.pid)
time.sleep(3.5)

# Try TCP and UDP to AutohostPort 8453
for proto_name, sock_type in [('UDP', socket.SOCK_DGRAM), ('TCP', socket.SOCK_STREAM)]:
    for addr in ['127.0.0.1', '::1']:
        af = socket.AF_INET6 if ':' in addr else socket.AF_INET
        try:
            s = socket.socket(af, sock_type)
            s.settimeout(1.0)
            if sock_type == socket.SOCK_STREAM:
                s.connect((addr, 8453))
                print(f'{proto_name} connected to {addr}:8453')
                s.sendall(b'forcestart\n')
                s.close()
            else:
                s.sendto(b'forcestart\n', (addr, 8453))
                print(f'{proto_name} sent to {addr}:8453')
                s.close()
        except Exception as e:
            print(f'{proto_name} {addr}:8453 failed: {e}')

time.sleep(3)
proc.terminate()
try:
    proc.wait(timeout=3)
except Exception:
    proc.kill()
    proc.wait()

print('Checking infolog...')
if os.path.exists(infolog):
    for line in open(infolog, 'r', encoding='utf-8', errors='ignore'):
        if any(k in line for k in ['Autohost', 'GameServer', 'Net', 'f=000', 'Phase 1', 'forcestart', 'Fatal', 'Error:']):
            print(line.strip())
else:
    print('No infolog found!')
