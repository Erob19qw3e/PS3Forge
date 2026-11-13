import argparse, copy, hashlib, json, os, re, secrets, shlex, shutil, subprocess, sys, threading, time, traceback, uuid, webbrowser, zipfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import xml.etree.ElementTree as ET
from forge_core import new_project, entity, validate, asset_info, obj_to_iyam, generate_scene, PID
from external_process import launch_external
import native_project
import local_build
import forge_package
import material_atlas
import material_library
import engine_features
from project_format import decode_project, encode_project

RESOURCES=Path(__file__).resolve().parent
ROOT=Path(os.environ.get('PS3FORGE_HOME',str(RESOURCES))).resolve()
DATA=ROOT/'data';PROJECTS=DATA/'projects';BUILDS=DATA/'builds'
for p in (PROJECTS,BUILDS):p.mkdir(parents=True,exist_ok=True)
TOKEN=secrets.token_hex(24)
DEFAULT_SETTINGS=dict(host='',user='',sdk='/opt/ps3dev',cg='/opt/ps3dev/lib',blender='',blenderLibs='',rpcs3='')
SETTINGS=DEFAULT_SETTINGS| (json.loads((DATA/'settings.json').read_text()) if (DATA/'settings.json').exists() else {})
for key,value in dict(buildMode='local',localDistro='PS3Forge',localSdk='/opt/ps3dev',localCg='/opt/ps3dev/lib').items():
    DEFAULT_SETTINGS[key]=value;SETTINGS.setdefault(key,value)
PASSWORD='';JOBS={};LOCK=threading.Lock();PROJECT_LOCKS={}

def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.parent/(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temp.open('w',encoding='utf8') as output:json.dump(value,output,indent=2,ensure_ascii=False);output.flush();os.fsync(output.fileno())
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
def project_dir(pid):
    if not PID.fullmatch(str(pid)):raise ValueError('Invalid project')
    return PROJECTS/pid
def load_project(pid):return native_project.hydrate(decode_project(json.loads((project_dir(pid)/'project.json').read_text(encoding='utf8'))),ROOT)

def list_projects():
    projects=[]
    for path in sorted(PROJECTS.glob('*/project.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            metadata=json.loads(path.read_text(encoding='utf8'));title=metadata['title']
            if not isinstance(title,str):raise ValueError('Invalid project title')
            projects.append(dict(id=path.parent.name,title=title,nativeProject=bool(metadata.get('nativeProject'))))
        except (ValueError,KeyError,OSError,TypeError) as error:
            projects.append(dict(id=path.parent.name,title='Unavailable project '+path.parent.name,nativeProject=False,error=str(error)))
    return projects
def save_project(p):
    pid=p.get('id','');project_dir(pid)
    with LOCK:guard=PROJECT_LOCKS.setdefault(pid,threading.RLock())
    with guard:return _save_project(p)

def _save_project(p):
    p=validate(p);root=project_dir(p['id'])
    for tid,t in p.get('textures',{}).items():material_library.read(root,tid,t)
    if p.get('materialAtlas'):material_atlas.read_project(root,p['materialAtlas'])
    if p.get('worldSectors'):
        import world_sectors
        world_sectors.read(root,p['worldSectors'])
    for aid,a in p['assets'].items():
        path=root/'assets'/a['file']
        if not path.is_file():raise ValueError('Missing asset file: '+a['name'])
        real=asset_info(path.read_bytes())
        for key in ('format','bones','events','groups','animationBytes'):a.pop(key,None)
        a.update(real)
    validate(p)
    target=root/'project.json';stored=encode_project(p)
    if target.exists() and not native_project.is_native(p):
        old=json.loads(target.read_text(encoding='utf8'))
        revision=hashlib.sha256(target.read_bytes()).hexdigest()
        if p.get('_revision') and p['_revision']!=revision:raise ValueError('Project changed on disk. Your draft is preserved; reopen or save it as another project before overwriting newer work.')
        if old.get('formatVersion',1)<3:
            backup=ROOT/'backups'/('project-format-v'+str(old.get('formatVersion',1))+'-'+p['id']+'-'+str(time.time_ns()))
            backup.mkdir(parents=True);shutil.copy2(target,backup/'project.json')
    stored.pop('_revision',None)
    if target.exists() and json.loads(target.read_text(encoding='utf8'))!=stored:
        history=root/'.history';history.mkdir(exist_ok=True);shutil.copy2(target,history/(str(time.time_ns())+'.json'))
    native_project.save_sources(p,ROOT);atomic(target,stored)
    if '_revision'in p:p['_revision']=hashlib.sha256(target.read_bytes()).hexdigest()
    return p

if not list(PROJECTS.glob('*/project.json')):
    p=new_project('Forge Starter');p['appid']='P3FGDEMO1';aid=uuid.uuid4().hex[:12];root=project_dir(p['id']);(root/'assets').mkdir(parents=True)
    sample=RESOURCES/'runtime/sample/knight.iyam'
    if sample.exists():
        raw=sample.read_bytes();(root/'assets'/(aid+'.iyam')).write_bytes(raw);p['assets'][aid]=dict(id=aid,name='Quaternius Knight',file=aid+'.iyam',source='Quaternius CC0',**asset_info(raw));p['scenes'][0]['entities'].append(entity('Knight','model',asset=aid,position=[2,0,0],color=[1,1,1],clip='Idle',script='Player',gravity=True,collider=True))
    p['scenes'][0]['entities'][1]['position']=[-2,1,0]
    save_project(p)

class SSHAuthRequired(Exception):
    code='SSH_AUTH_REQUIRED'

def ssh_connect(password=None):
    import paramiko
    client=paramiko.SSHClient();client.load_system_host_keys()
    known=Path.home()/'.ssh/known_hosts'
    if known.exists():client.load_host_keys(str(known))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    secret=PASSWORD if password is None else password
    try:
        client.connect(SETTINGS['host'],username=SETTINGS['user'],password=secret or None,timeout=15,auth_timeout=15,look_for_keys=not bool(secret),allow_agent=not bool(secret))
    except paramiko.AuthenticationException:
        client.close()
        raise SSHAuthRequired('SSH sign-in failed. Check your password and try again.') from None
    except paramiko.SSHException as e:
        client.close()
        if 'No authentication methods available' in str(e):
            raise SSHAuthRequired('Enter your SSH password for this session. No usable SSH keys are available.') from None
        raise
    except Exception:
        client.close();raise
    return client
def remote_exec(client,command,log=None,timeout=300):
    _,stdout,stderr=client.exec_command(command,timeout=timeout);channel=stdout.channel;chunks=[];deadline=time.time()+timeout
    while True:
        for ready,read in ((channel.recv_ready,channel.recv),(channel.recv_stderr_ready,channel.recv_stderr)):
            while ready():
                s=read(32768).decode('utf8','replace');chunks.append(s)
                if log:log(s)
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():break
        if time.time()>deadline:channel.close();raise TimeoutError('SSH operation timed out')
        time.sleep(.03)
    code=channel.recv_exit_status();output=''.join(chunks)
    if code:raise RuntimeError('Remote command failed ('+str(code)+')\n'+output[-7000:])
    return output
def remote_mkdir(sftp,path):
    parts=path.split('/');current=''
    for part in parts:
        if not part:continue
        current+='/'+part
        try:sftp.stat(current)
        except IOError:sftp.mkdir(current)
def upload_tree(sftp,local,remote):
    remote_mkdir(sftp,remote)
    for p in Path(local).rglob('*'):
        if p.is_dir():continue
        target=remote+'/'+p.relative_to(local).as_posix();remote_mkdir(sftp,target.rsplit('/',1)[0]);sftp.put(str(p),target)
def download_tree(sftp,remote,local):
    import stat
    local=Path(local);local.mkdir(parents=True,exist_ok=True)
    for entry in sftp.listdir_attr(remote):
        if stat.S_ISDIR(entry.st_mode):download_tree(sftp,remote+'/'+entry.filename,local/entry.filename)
        else:sftp.get(remote+'/'+entry.filename,str(local/entry.filename))
def job_start(fn):
    with LOCK:
        if any(j['status']=='running' for j in JOBS.values()):raise ValueError('Wait for the current operation to finish')
        jid=uuid.uuid4().hex[:12];JOBS[jid]=dict(id=jid,status='running',log='',phase='Preparing')
    def worker():
        j=JOBS[jid]
        try:result=fn(j);j.update(status='done',result=result,phase='Completed')
        except Exception as e:j.update(status='error',phase='Error',error=str(e),code=getattr(e,'code',None));j['log']+='\n'+(str(e) if isinstance(e,SSHAuthRequired) else traceback.format_exc())
    threading.Thread(target=worker,daemon=True).start();return dict(job=jid)

def prepare_build(p,out):
    p=validate(p)
    if native_project.is_native(p):
        native_project.prepare(p,ROOT,out);atomic(out/'project.forge.json',p);return
    runtime=RESOURCES/'runtime'
    for folder in ['source','include','shaders','support','tools']:shutil.copytree(runtime/folder,out/folder,dirs_exist_ok=True)
    # Game-specific files from the original demo are never compiled into Forge.
    for name in ['Makefile','sfo.xml','ICON0.PNG','LICENSE-PSL1GHT.txt']:shutil.copy2(runtime/name,out/name)
    if p.get('materialAtlas'):material_atlas.write_header(project_dir(p['id']),p['materialAtlas'],out/'include/forge_atlas.h')
    material_library.write_header(p,project_dir(p['id']),out/'include/forge_materials.h')
    generate_scene(p,out)
    pkg=out/'pkgfiles';(pkg/'USRDIR/assets').mkdir(parents=True)
    shutil.copy2(out/'ICON0.PNG',pkg/'ICON0.PNG')
    for a in p['assets'].values():shutil.copy2(project_dir(p['id'])/'assets'/a['file'],pkg/'USRDIR/assets'/a['file'])
    if p.get('worldSectors'):
        import world_sectors
        raw=world_sectors.read(project_dir(p['id']),p['worldSectors']);(pkg/'USRDIR/world').mkdir();(pkg/'USRDIR/world/world.fws').write_bytes(raw)
    make=(out/'Makefile').read_text();safe=re.sub('[^A-Za-z0-9 ._-]','_',p['title'])
    make=re.sub(r'^TITLE\s*:=.*$',lambda _: 'TITLE := '+safe,make,flags=re.M);make=re.sub(r'^APPID\s*:=.*$',lambda _: 'APPID := '+p['appid'],make,flags=re.M);(out/'Makefile').write_text(make)
    tree=ET.parse(out/'sfo.xml')
    for value in tree.getroot():
        if value.attrib.get('name')=='APP_VER':value.text=p['version']
        if value.attrib.get('name')=='TITLE':value.text=p['title']
        if value.attrib.get('name')=='TITLE_ID':value.text=p['appid']
    tree.write(out/'sfo.xml',encoding='utf8',xml_declaration=True)
    atomic(out/'project.forge.json',p)

def build_job(p,j):
    out=BUILDS/j['id'];out.mkdir();prepare_build(p,out);j['project']=p['id'];j['appid']=p['appid'];j['phase']='Uploading to Ubuntu server'
    if SETTINGS.get('buildMode')=='local':
        j['phase']='Building locally (WSL)'
        def log_local(s):j['log']=(j['log']+s)[-150000:]
        try:local_build.build(dict(SETTINGS),out,p,log_local)
        finally:(out/'build.log').write_text(j['log'],encoding='utf8')
        atomic(out/'result.json',dict(project=p['id'],appid=p['appid'],title=p['title'],version=p['version'],backend='local'))
        return dict(download='/download/'+j['id']+'/game.pkg',appid=p['appid'],bytes=(out/'game.pkg').stat().st_size,backend='local')
    if SETTINGS.get('buildMode')!='ssh':raise ValueError('Select Local (WSL) or Remote SSH in Settings')
    remote='/home/'+SETTINGS['user']+'/ps3-forge-builds/'+j['id']
    client=ssh_connect()
    try:
        sftp=client.open_sftp();upload_tree(sftp,out,remote);j['phase']='Building PPU executable and PKG'
        env='export PS3DEV='+shlex.quote(SETTINGS['sdk'])+' PSL1GHT='+shlex.quote(SETTINGS['sdk'])+'; export PATH="$PS3DEV/bin:$PS3DEV/ppu/bin:$PS3DEV/spu/bin:$PATH"; export LD_LIBRARY_PATH='+shlex.quote(SETTINGS['cg'])+'; '
        def log(s):j['log']=(j['log']+s)[-150000:]
        command='set -e; '+env+'cd '+shlex.quote(remote)+'; make -j2; make pkg; python3 tools/verify_package.py --project . --appid '+shlex.quote(p['appid'])+' --app-version '+shlex.quote(p['version'])
        remote_exec(client,command,log,600);j['phase']='Downloading results'
        sftp.get(remote+'/'+j['id']+'.gnpdrm.pkg',str(out/'game.pkg'));download_tree(sftp,remote+'/build/pkg',out/'staging')
        (out/'build.log').write_text(j['log'],encoding='utf8');sftp.close()
    finally:client.close()
    atomic(out/'result.json',dict(project=p['id'],appid=p['appid'],title=p['title'],version=p['version']))
    return dict(download='/download/'+j['id']+'/game.pkg',appid=p['appid'],bytes=(out/'game.pkg').stat().st_size)

def import_job(pid,name,raw,j):
    p=load_project(pid)
    p['_revision']=hashlib.sha256((project_dir(pid)/'project.json').read_bytes()).hexdigest()
    if native_project.is_native(p):raise ValueError('Scene import is unavailable for native voxel projects')
    aid=uuid.uuid4().hex[:12];assetdir=project_dir(pid)/'assets';assetdir.mkdir(exist_ok=True)
    suffix=Path(name).suffix.lower();source='Imported '+suffix
    if suffix=='.iyam':converted=raw
    elif suffix=='.obj':converted=obj_to_iyam(raw.decode('utf-8-sig'))
    elif suffix=='.glb':
        import glb_import
        j['phase']='Importing skeleton, animations and materials locally';result=glb_import.convert(raw);converted=result['model']
        p.setdefault('materials',{}).update(result['materials']);p.setdefault('textures',{}).update(result['textures'])
    else:raise ValueError('Import OBJ, GLB or IYAM')
    info=asset_info(converted)
    p['assets'][aid]=dict(id=aid,name=Path(name).stem[:60],file=aid+'.iyam',source=source,**info)
    if suffix=='.glb':p['assets'][aid]['defaultMaterials']=result['defaultMaterials']
    validate(p)
    with (assetdir/(aid+'.iyam')).open('xb') as output:output.write(converted)
    if suffix=='.glb':
        for filename,payload in result['files'].items():
            target=project_dir(pid)/filename;target.parent.mkdir(exist_ok=True)
            with target.open('xb') as output:output.write(payload)
    p=save_project(p)
    return dict(project=encode_project(p),asset=aid)

class Handler(BaseHTTPRequestHandler):
    def local_host(self):
        if self.headers.get('Host','').split(':')[0] not in ('127.0.0.1','localhost'):
            raise ValueError('Access is limited to localhost')
    def log_message(self,*args):pass
    def reply(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def file(self,path,download_name=None):
        if not path.is_file():raise FileNotFoundError('File is unavailable')
        import mimetypes
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(str(path))[0] or 'application/octet-stream');self.send_header('Content-Length',str(path.stat().st_size))
        if download_name:self.send_header('Content-Disposition','attachment; filename="'+forge_package.safe_name(Path(download_name).stem)+'.forgepack"')
        self.end_headers()
        with path.open('rb') as f:shutil.copyfileobj(f,self.wfile)
    def do_GET(self):
        try:
            self.local_host()
            q=urlparse(self.path);params=parse_qs(q.query);path=q.path
            if path=='/api/config':return self.reply(dict(token=TOKEN,settings=SETTINGS,authenticated=bool(PASSWORD),version='0.9.8',projectFormatVersion=4,projects=list_projects()))
            if path=='/api/world-preview':
                p=load_project(params['id'][0]);m=p.get('worldSectors')
                if not m:raise ValueError('Project has no streamed world')
                sidecar=project_dir(p['id'])/'world/editor-preview.json';extra={}
                if sidecar.is_file() and sidecar.stat().st_size<=2*1024*1024:
                    candidate=json.loads(sidecar.read_text(encoding='utf8'))
                    if candidate.get('sha256')==m['sha256']:extra=candidate
                ranges=extra.get('hiddenRanges',[])
                if not isinstance(ranges,list)or len(ranges)>128 or any(not isinstance(v,list)or len(v)!=2 or any(type(x)is not int for x in v)or not 0<=v[0]<=v[1]<=m['instances']for v in ranges):raise ValueError('Invalid world preview ranges')
                labels=extra.get('labels',{})
                if not isinstance(labels,dict)or len(labels)>4096 or any(not k.isdigit()or not 0<=int(k)<m['models']or not isinstance(v,str)or len(v)>200 for k,v in labels.items()):raise ValueError('Invalid world preview labels')
                scene=next((i for i,s in enumerate(p['scenes'])if any(e['id']==m['target']for e in s['entities'])),p['activeScene'])
                return self.reply(dict(url='/world/'+p['id']+'/world.fws',sha256=m['sha256'],scene=scene,hiddenRanges=ranges,labels=labels))
            if path.startswith('/world/'):
                _,_,pid,name=path.split('/')
                if name!='world.fws':raise ValueError('Unknown world resource')
                p=load_project(pid)
                if not p.get('worldSectors'):raise ValueError('Project has no streamed world')
                return self.file(project_dir(pid)/'world/world.fws')
            if path=='/api/engine-schema':return self.reply(engine_features.SCHEMA)
            if path=='/api/project':
                pid=params['id'][0];p=load_project(pid);p['_revision']=hashlib.sha256((project_dir(pid)/'project.json').read_bytes()).hexdigest();return self.reply(encode_project(p))
            if path=='/api/assets/status':
                pid=params['id'][0];p=load_project(pid);result={}
                for aid,a in p['assets'].items():
                    f=project_dir(pid)/'assets'/a['file'];stat=f.stat();result[aid]=str(stat.st_mtime_ns)+':'+str(stat.st_size)
                for tid,t in p.get('textures',{}).items():
                    f=project_dir(pid)/'textures'/t['file'];stat=f.stat();result['texture:'+tid]=str(stat.st_mtime_ns)+':'+str(stat.st_size)
                return self.reply(result)
            if path=='/api/assets/refresh':
                pid=params['id'][0];p=load_project(pid);result={}
                for aid,a in p['assets'].items():
                    try:
                        value=dict(a)
                        for key in ('format','bones','events','groups','animationBytes'):value.pop(key,None)
                        value.update(asset_info((project_dir(pid)/'assets'/a['file']).read_bytes()));result[aid]=value
                    except Exception as error:raise ValueError(a['name']+' / Asset reload: '+str(error)) from error
                textures={}
                for tid,t in p.get('textures',{}).items():textures[tid]=dict(t,**material_library.current(project_dir(pid),tid))
                return self.reply(dict(assets=result,textures=textures))
            if path.startswith('/texture/'):
                _,_,pid,name=path.split('/')
                p=load_project(pid)
                if name=='atlas.png':material_atlas.read_project(project_dir(pid),p['materialAtlas'])
                else:
                    tid=Path(name).stem
                    if name!=tid+'.png':raise ValueError('Unknown project texture')
                    material_library.current(project_dir(pid),tid)
                return self.file(project_dir(pid)/'textures'/name)
            if path=='/api/package/download':
                uid=params['id'][0]
                if not PID.fullmatch(uid):raise ValueError('Invalid package ID')
                root=DATA/'packages/exports';meta=json.loads((root/(uid+'.json')).read_text())
                return self.file(root/(uid+'.forgepack'),meta['filename'])
            if path=='/api/native-preview':
                p=load_project(params['id'][0]);native_project.check(p)
                if not native_project.is_native(p):raise ValueError('Not a native project')
                return self.file(ROOT/'outputs/Block-Garden-RPCS3.png')
            if path=='/api/last-build':
                pid=params['id'][0];project_dir(pid)
                matches=[]
                for f in BUILDS.glob('*/result.json'):
                    m=json.loads(f.read_text())
                    if m['project']==pid and (f.parent/'game.pkg').is_file():matches.append(f)
                f=max(matches,key=lambda x:x.stat().st_mtime) if matches else None
                return self.reply(dict(job=f.parent.name,download='/download/'+f.parent.name+'/game.pkg') if f else {})
            if path=='/api/export':
                pid=params['id'][0];root=project_dir(pid);load_project(pid)
                output=DATA/(pid+'.zip')
                with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
                    for f in root.rglob('*'):
                        if f.is_file():z.write(f,f.relative_to(root))
                    p=load_project(pid)
                    if native_project.is_native(p):
                        native=native_project.root(ROOT)
                        for folder in ('source','include','shaders','support','tools','tests'):
                            for f in (native/folder).rglob('*'):
                                if f.is_file():z.write(f,Path('native')/f.relative_to(native))
                        for name in ('Makefile','sfo.xml','ICON0.PNG','LICENSE-PSL1GHT.txt','LICENSE.txt','LEGGIMI.md'):
                            if (native/name).is_file():z.write(native/name,Path('native')/name)
                return self.file(output)
            if path=='/api/job':return self.reply(JOBS[params['id'][0]])
            if path.startswith('/asset/'):
                _,_,pid,name=path.split('/');root=(project_dir(pid)/'assets').resolve();target=(root/name).resolve()
                if target.parent!=root:raise ValueError('Invalid path')
                return self.file(target)
            if path.startswith('/download/'):
                _,_,jid,name=path.split('/')
                if not PID.fullmatch(jid) or name not in ('game.pkg','build.log'):raise ValueError('Invalid download')
                return self.file(BUILDS/jid/name)
            target=(RESOURCES/'web'/unquote(path.lstrip('/') or 'index.html')).resolve()
            if not target.is_relative_to((RESOURCES/'web').resolve()):raise ValueError('Invalid path')
            return self.file(target)
        except Exception as e:self.reply(dict(error=str(e)),404)
    def do_POST(self):
        global PASSWORD
        try:
            self.local_host()
            if self.headers.get('X-Forge-Token')!=TOKEN:raise ValueError('Local token is missing')
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=100*1024*1024:raise ValueError('Request is too large or empty')
            raw=self.rfile.read(n);path=urlparse(self.path).path
            if path=='/api/texture/import':
                pid=self.headers['X-Project'];root=project_dir(pid);tid=uuid.uuid4().hex[:12];metadata,png=material_library.convert(raw,tid)
                folder=root/'textures';folder.mkdir(exist_ok=True);(folder/metadata['file']).write_bytes(png)
                return self.reply(dict(id=tid,metadata=metadata))
            if path=='/api/package/inspect':
                bundle=forge_package.inspect_package(raw,RESOURCES);uid=uuid.uuid4().hex[:12]
                folder=DATA/'packages/incoming';folder.mkdir(parents=True,exist_ok=True);(folder/(uid+'.forgepack')).write_bytes(raw)
                return self.reply(dict(upload=uid,**forge_package.summary(bundle)))
            if path=='/api/import':return self.reply(job_start(lambda j:import_job(self.headers['X-Project'],unquote(self.headers['X-Filename']),raw,j)))
            d=json.loads(raw)
            if path=='/api/project/copy':
                source=validate(d['project'])
                if source.get('nativeProject'):raise ValueError('Save copies of native source projects through their source workspace')
                old=project_dir(source['id']);p=copy.deepcopy(source);p.pop('_revision',None);p.update(id=uuid.uuid4().hex[:12],title=str(d.get('title',source['title']+' Copy'))[:60]);p['appid']='P3'+p['id'][:7].upper();root=project_dir(p['id']);(root/'assets').mkdir(parents=True);(root/'textures').mkdir()
                for a in p['assets'].values():shutil.copy2(old/'assets'/a['file'],root/'assets'/a['file'])
                for name in ['atlas.png']+[t['file'] for t in p.get('textures',{}).values()]:
                    if (old/'textures'/name).exists():shutil.copy2(old/'textures'/name,root/'textures'/name)
                if p.get('worldSectors'):shutil.copytree(old/'world',root/'world')
                save_project(p);return self.reply(dict(project=encode_project(p)))
            if path=='/api/package/export':
                p=validate(d['project']);project_dir(p['id'])
                payload,filename=forge_package.export_package(p,d['objects'],project_dir(p['id']),RESOURCES,d.get('name',''))
                uid=uuid.uuid4().hex[:12];folder=DATA/'packages/exports';folder.mkdir(parents=True,exist_ok=True)
                (folder/(uid+'.forgepack')).write_bytes(payload);atomic(folder/(uid+'.json'),dict(filename=filename))
                return self.reply(dict(download='/api/package/download?id='+uid,filename=filename,bytes=len(payload)))
            if path=='/api/package/import':
                uid=d['upload']
                if not PID.fullmatch(str(uid)):raise ValueError('Invalid package ID')
                bundle=forge_package.inspect_package((DATA/'packages/incoming'/(uid+'.forgepack')).read_bytes(),RESOURCES)
                fresh=d.get('newProject') is True
                p,files=forge_package.merge_package(bundle,None if fresh else d['project'])
                root=project_dir(p['id'])
                if fresh and root.exists():raise ValueError('Project ID is already in use; retry the import')
                atlas_payload=bundle['files'].get('textures/atlas.png')
                atlas_target=root/'textures/atlas.png'
                if atlas_payload and atlas_target.exists() and atlas_target.read_bytes()!=atlas_payload:raise ValueError('Existing project atlas must not be overwritten')
                (root/'assets').mkdir(parents=True,exist_ok=True)
                for filename,payload in files.items():
                    target=root/filename if filename.startswith(('textures/','world/')) else root/'assets'/filename
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with target.open('xb') as output:output.write(payload)
                if atlas_payload and not atlas_target.exists():
                    atlas_target.parent.mkdir(parents=True,exist_ok=True)
                    with atlas_target.open('xb') as output:output.write(atlas_payload)
                docs_id=uuid.uuid4().hex[:12]
                for name,payload in bundle['files'].items():
                    if name.startswith('docs/'):
                        folder=root/'package-docs'/docs_id;folder.mkdir(parents=True,exist_ok=True)
                        with (folder/Path(name).name).open('xb') as output:output.write(payload)
                if fresh:save_project(p)
                # Existing drafts are returned to the editor; explicit Save commits
                # the project JSON. New asset IDs never replace existing files.
                return self.reply(dict(project=encode_project(p),newProject=fresh,name=bundle['name']))
            if path=='/api/session-login':
                secret=d.get('password')
                if not isinstance(secret,str) or not 0<len(secret)<=1024:raise SSHAuthRequired('Enter your SSH password.')
                c=ssh_connect(password=secret);c.close()
                PASSWORD=secret
                return self.reply(dict(ok=True))
            if path=='/api/save':return self.reply(encode_project(save_project(d)))
            if path=='/api/new':p=new_project(d.get('title','My PS3 Game'));save_project(p);return self.reply(encode_project(p))
            if path=='/api/settings':
                for key in DEFAULT_SETTINGS:
                    if key in d:SETTINGS[key]=str(d[key])[:500]
                if 'password' in d:PASSWORD=d['password']
                atomic(DATA/'settings.json',SETTINGS);return self.reply(dict(ok=True))
            if path=='/api/test-ssh':
                c=ssh_connect()
                try:result=remote_exec(c,shlex.quote(SETTINGS['sdk']+'/ppu/bin/ppu-gcc')+' --version')
                finally:c.close()
                return self.reply(dict(output=result))
            if path=='/api/test-local':return self.reply(dict(output=local_build.check(dict(SETTINGS))))
            if path=='/api/build':
                p=save_project(d);return self.reply(job_start(lambda j:build_job(copy.deepcopy(p),j)))
            if path=='/api/rpcs3':
                jid=d['job']
                if not PID.fullmatch(jid):raise ValueError('Invalid build')
                out=BUILDS/jid;meta=json.loads((out/'result.json').read_text());exe=Path(SETTINGS['rpcs3'])
                if not exe.is_file():raise ValueError('RPCS3 was not found: check Settings')
                if (exe.parent/'portable').exists():raise ValueError('RPCS3 uses a portable folder. Select a standard RPCS3 installation in Settings.')
                profile=ROOT/'rpcs3-profile';profile.mkdir(exist_ok=True)
                if not (profile/'dev_flash/vsh').exists():
                    firmware=exe.parent/'dev_flash'
                    if not (firmware/'vsh').exists():raise ValueError('RPCS3 firmware is missing: install it in your RPCS3 installation before testing')
                    shutil.copytree(firmware,profile/'dev_flash',dirs_exist_ok=True)
                dest=profile/'dev_hdd0/game'/meta['appid'];marker=dest/'forge-project.json'
                if dest.exists() and not marker.exists():raise ValueError('An existing RPCS3 folder is not managed by Forge: install the PKG manually')
                shutil.copytree(out/'staging',dest,dirs_exist_ok=True);atomic(marker,meta)
                env=os.environ.copy();env['RPCS3_CONFIG_DIR']=str(profile)+os.sep
                process=launch_external([str(exe),'--no-gui',str(dest/'USRDIR/EBOOT.BIN')],cwd=exe.parent,env=env)
                return self.reply(dict(ok=True,pid=process.pid))
            raise ValueError('Unknown operation')
        except Exception as e:self.reply(dict(error=str(e),code=getattr(e,'code',None)),400)

if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('--port',type=int,default=8780);args.add_argument('--open',action='store_true');options=args.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',options.port),Handler)
    if options.open:threading.Timer(.8,lambda:webbrowser.open('http://127.0.0.1:'+str(options.port))).start()
    print('PS3 Forge: http://127.0.0.1:'+str(options.port),flush=True);server.serve_forever()
