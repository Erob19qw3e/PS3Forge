"""Local WSL build backend. Does not connect to or fall back to SSH."""
import os
import queue
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path
from external_process import launch_external


def run_wsl(settings, command, log=None, timeout=900):
    distro=settings.get('localDistro','PS3Forge')
    if not isinstance(distro,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',distro):
        raise ValueError('Invalid WSL distribution name')
    def popen(*args,**kwargs):
        kwargs.update(stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return subprocess.Popen(*args,**kwargs)
    process=launch_external(['wsl.exe','--distribution',distro,'--user','root','--exec','bash','-lc',command],cwd=Path.home(),popen=popen)
    output=[];events=queue.Queue();deadline=time.monotonic()+timeout
    def read():
        try:
            for raw in iter(process.stdout.readline,b''):events.put(raw)
        finally: events.put(None)
    threading.Thread(target=read,daemon=True).start()
    while True:
        if time.monotonic()>deadline:
            process.terminate();process.wait(timeout=10)
            raise TimeoutError('Local build timed out')
        try:raw=events.get(timeout=.1)
        except queue.Empty:continue
        if raw is None:break
        text=raw.decode('utf-16le' if b'\x00' in raw else 'utf8','replace');output.append(text)
        if log:log(text)
    code=process.wait(timeout=10);text=''.join(output)
    if code:raise RuntimeError('Local compiler failed ('+str(code)+')\n'+text[-7000:])
    return text


def environment(settings):
    sdk=settings.get('localSdk','/opt/ps3dev')
    cg=settings.get('localCg','/opt/ps3dev/lib')
    if not isinstance(sdk,str) or not sdk.startswith('/') or not isinstance(cg,str) or not cg.startswith('/'):
        raise ValueError('Local SDK and Cg paths must be absolute Linux paths')
    return ('export PS3DEV='+shlex.quote(sdk)+' PSL1GHT='+shlex.quote(sdk)+'; '
            'export PATH="$PS3DEV/bin:$PS3DEV/ppu/bin:$PS3DEV/spu/bin:$PATH"; '
            'export LD_LIBRARY_PATH='+shlex.quote(cg)+':"$PS3DEV/lib:${LD_LIBRARY_PATH:-}"; ')


def check(settings):
    return run_wsl(settings,'set -e; '+environment(settings)+
        'test -f "$PSL1GHT/ppu_rules"; command -v make; command -v python3; ppu-gcc --version; command -v cgcomp; '
        'python3 -c '+shlex.quote('import ctypes; ctypes.CDLL("libCg.so"); print("Cg library ready")'),timeout=30)


def build(settings,out,project,log):
    out=Path(out).resolve()
    if not re.fullmatch(r'[a-f0-9]{12}',out.name):raise ValueError('Invalid build directory')
    # Convert through wslpath, then compile on Linux storage (spaces are quoted).
    mounted=run_wsl(settings,'wslpath -a '+shlex.quote(str(out)),timeout=30).strip()
    if not mounted.startswith('/'):raise RuntimeError('Cannot access the Windows project from WSL')
    destination='/root/ps3forge-builds/'+out.name
    command=('set -e; '+environment(settings)+'mkdir -p /root/ps3forge-builds; '
        'test ! -e '+shlex.quote(destination)+'; cp -a '+shlex.quote(mounted)+' '+shlex.quote(destination)+'; '
        'cd '+shlex.quote(destination)+'; make -j2; make pkg; '
        'python3 tools/verify_package.py --project . --appid '+shlex.quote(project['appid'])+
        ' --app-version '+shlex.quote(project['version'])+'; '
        'cp '+shlex.quote(out.name+'.gnpdrm.pkg')+' '+shlex.quote(mounted+'/game.pkg')+'; '
        'mkdir -p '+shlex.quote(mounted+'/staging')+'; cp -a build/pkg/. '+shlex.quote(mounted+'/staging/'))
    return run_wsl(settings,command,log,900)
