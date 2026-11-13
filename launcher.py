import subprocess, sys, urllib.request, webbrowser, time
from pathlib import Path
root=Path(__file__).resolve().parent
exe=root/'desktop-dist-0.9.1/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.9.0/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.8.2/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.8.1/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.7.1/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.7/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.6/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.5/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.4/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.3.1-release/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.3.1/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist-0.3/PS3Forge/PS3Forge.exe'
if not exe.is_file():exe=root/'desktop-dist/PS3Forge/PS3Forge.exe'
if exe.is_file():
 subprocess.Popen([str(exe)],cwd=exe.parent)
 sys.exit(0)
url='http://127.0.0.1:8780'
try:
 with urllib.request.urlopen(url+'/api/config',timeout=2) as r:
  if not r.read().startswith(b'{'):raise RuntimeError('Porta 8780 occupata')
except OSError:
 subprocess.Popen([sys.executable,str(root/'server.py')],cwd=root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 for i in range(30):
  try:
   urllib.request.urlopen(url+'/api/config',timeout=1).close();break
  except OSError:time.sleep(.3)
 else:raise RuntimeError('Avvio non riuscito: controlla che la porta 8780 sia libera')
webbrowser.open(url)
