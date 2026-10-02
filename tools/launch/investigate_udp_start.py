import socket, subprocess, time, pathlib, re
ROOT = pathlib.Path(r'C:\tmp\bar-tc-repo')
rt = ROOT / 'tools/runtime-autohost-probe'
script_path = rt / 'startscript.txt'
script_original = script_path.read_text()
script_path.write_text(script_original.replace('AutohostPort=8455;', 'AutohostPort=8456;'))
# Configuration, NOT startscript, selects the autohost destination.
cfg = rt / 'springsettings.cfg'
original = cfg.read_text()
cfg.write_text(original + '\nAutohostIP=127.0.0.1\nAutohostPort=8456\nServerLogInfoMessages=1\n')
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('127.0.0.1',8456)); s.settimeout(.2)
p = subprocess.Popen([str(ROOT/'tools/engine/recoil_2026.07.04/spring-headless.exe'),'--isolation','--write-dir',str(rt),str(rt/'startscript.txt')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
peer = None
try:
    deadline=time.monotonic()+15
    sent=False
    while time.monotonic()<deadline:
        try:
            data,peer=s.recvfrom(65535)
            print('EVENT',data[:160],peer)
        except socket.timeout: pass
        if peer and not sent and time.monotonic()>deadline-8:
            s.sendto(b'/forcestart',peer); sent=True
            print('SENT /forcestart TO',peer)
    log=(rt/'infolog.txt').read_text(errors='replace')
    frames=[int(x) for x in re.findall(r'\[f=(-?\d+)\]',log)]
    print('MAX FRAME',max(frames) if frames else None)
    print('\n'.join(log.splitlines()[-12:]))
finally:
    p.terminate(); p.wait(timeout=5); s.close(); cfg.write_text(original); script_path.write_text(script_original)
