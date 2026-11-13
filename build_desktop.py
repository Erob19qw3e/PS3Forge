from pathlib import Path
import os
# Build with only the venv and Windows DLL search paths. Unrelated tools can ship
# DLLs with the same name (e.g. Poppler ICU), but incompatible exported symbols.
os.environ['PATH']=os.pathsep.join([str(Path(__file__).resolve().parent/'.venv/Scripts'),str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot']])
from PyInstaller.__main__ import run
root=Path(__file__).resolve().parent
args=['--clean','--noconfirm','--icon',str(root/'forge.ico'),'--onedir','--windowed','--noupx','--name','PS3Forge','--distpath',str(root/os.environ.get('PS3FORGE_DIST','desktop-dist-0.9.8')),'--workpath',str(root/'desktop-build/work'),'--specpath',str(root/'desktop-build'),'--hidden-import','paramiko']
for name in ['web','runtime','bake_glb.py','LICENSE.txt','THIRD_PARTY','DESKTOP.md','HELP.md','SCRIPTING.md','PACKAGES.md','ENGINE-0.9.md','WORLD-SECTORS.md','AGENTS.md']:
 args+=['--add-data',str(root/name)+';'+(name if (root/name).is_dir() else '.')]
args+=[str(root/'desktop.py')]
run(args)
