"""Source-backed native projects; no user saves enter build or export folders."""
import hashlib, os, shutil, time
from pathlib import Path

PROJECT_ID = 'b10c6a4d0002'
FILES = ('source/main.cpp', 'include/voxel.h', 'include/savegame.h',
         'source/rsxutil.cpp', 'shaders/diffuse_specular_shader.vcg',
         'shaders/diffuse_specular_shader.fcg')

def is_native(p):
    return p.get('nativeProject') == 'block-garden-v1'

def check(p):
    if not is_native(p): return
    if (p['id'],p['appid'],p['title'],p['version']) != (PROJECT_ID,'P3BLKG001','Block Garden','01.00'):
        raise ValueError('The native Block Garden project keeps the title, ID and version from its Makefile.')
    if p.get('assets') or p.get('scripts') or any(s.get('entities') for s in p['scenes']):
        raise ValueError('Edit the voxel world in its C++ source files.')
    files=p.get('nativeFiles',{})
    if set(files)!=set(FILES) or any(not isinstance(s,str) or len(s)>500000 for s in files.values()):
        raise ValueError('Invalid native source file list')

def root(home): return Path(home)/'games/BlockGarden'
def digest(text): return hashlib.sha256(text.encode('utf8')).hexdigest()

def hydrate(p,home):
    if is_native(p):
        p['nativeFiles']={name:(root(home)/name).read_text(encoding='utf8') for name in FILES}
        p['nativeHashes']={name:digest(text) for name,text in p['nativeFiles'].items()}
    return p

def save_sources(p,home):
    if not is_native(p): return
    check(p); changes=[]
    for name,text in p['nativeFiles'].items():
        target=root(home)/name; current=target.read_text(encoding='utf8')
        if current==text: continue
        if p.get('nativeHashes',{}).get(name)!=digest(current):
            raise ValueError('Source file changed outside the editor: '+name+'. Reopen the project before saving.')
        changes.append((name,target,text))
    backup=Path(home)/'backups'/('block-garden-source-'+str(time.time_ns()))
    for name,target,text in changes:
        dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,dest)
        temp=target.with_suffix(target.suffix+'.forge-tmp');temp.write_text(text,encoding='utf8');os.replace(temp,target)
    p['nativeHashes']={name:digest(text) for name,text in p['nativeFiles'].items()}

def prepare(p,home,out):
    check(p); source=root(home);out=Path(out)
    for folder in ('source','include','shaders','support','tools'):
        shutil.copytree(source/folder,out/folder,dirs_exist_ok=True)
    for name in ('Makefile','sfo.xml','ICON0.PNG','LICENSE-PSL1GHT.txt'):
        shutil.copy2(source/name,out/name)
    for name,text in p['nativeFiles'].items(): (out/name).write_text(text,encoding='utf8')
    pkg=out/'pkgfiles';(pkg/'USRDIR').mkdir(parents=True,exist_ok=True)
    shutil.copy2(source/'ICON0.PNG',pkg/'ICON0.PNG')
