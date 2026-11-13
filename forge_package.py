"""Portable, versioned scene fragments. Import validates data; it never runs code."""
import copy
import hashlib
import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from forge_core import validate,asset_info,new_project,PID
from project_format import encode_project
import material_atlas
import material_library

FORMAT='PS3Forge.Package'
LIMIT=96*1024*1024

def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe_name(name):
    value=re.sub(r'[^A-Za-z0-9 _-]','_',name).strip()[:55] or 'Forge package'
    if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',value,re.I):value='Forge '+value
    return value

def export_package(value,ids,project_root,resources,name=''):
    p=validate(value)
    if p.get('nativeProject'):raise ValueError('Native source projects cannot be exported as object packages')
    if not isinstance(ids,list) or not ids or len(ids)>128 or len(set(ids))!=len(ids):raise ValueError('Select one or more objects')
    lookup={e['id']:e for s in p['scenes'] for e in s['entities']}
    if any(i not in lookup for i in ids):raise ValueError('An exported object no longer exists')
    # Follow component references so attachments/cameras/NPCs remain usable.
    ids=list(ids)
    for eid in ids:
        for component in lookup[eid].get('engine',{}).values():
            target=component.get('target')
            if target and target not in ids:ids.append(target)
    entities=[copy.deepcopy(lookup[i]) for i in ids]
    title=safe_name(name or (entities[0]['name'] if len(entities)==1 else p['title']))
    fragment=new_project(title)
    fragment.update(scripts=copy.deepcopy(p['scripts']),assets={},camera=copy.deepcopy(p['camera']),background=p['background'])
    for key in ('useForgeAtlas','crosshair','runtimeHud','materialAtlas'):
        if key in p:fragment[key]=copy.deepcopy(p[key])
    fragment['scenes']=[dict(name=title,entities=entities)]
    files={}
    if p.get('worldSectors')and p['worldSectors']['target']in ids:
        import world_sectors
        fragment['worldSectors']=copy.deepcopy(p['worldSectors']);files['world/world.fws']=world_sectors.read(project_root,p['worldSectors'])
    asset_ids={e['asset'] for e in entities if e['kind']=='model'}
    asset_ids.update(level['asset'] for e in entities for level in e.get('engine',{}).get('LOD',{}).get('levels',[]))
    for aid in sorted(asset_ids):
        raw=(Path(project_root)/'assets'/(aid+'.iyam')).read_bytes();info=asset_info(raw)
        fragment['assets'][aid]=copy.deepcopy(p['assets'][aid]);fragment['assets'][aid].update(info)
        files['assets/'+aid+'.iyam']=raw
    mids={mid for e in entities for mid in e.get('materials',[]) if mid}
    mids.update(mid for a in fragment['assets'].values() for mid in a.get('defaultMaterials',[]) if mid)
    fragment['materials']={mid:copy.deepcopy(p['materials'][mid]) for mid in mids}
    tids={m['texture'] for m in fragment['materials'].values() if m['texture']}
    fragment['textures']={tid:copy.deepcopy(p['textures'][tid]) for tid in tids}
    for tid,meta in fragment['textures'].items():files['textures/'+meta['file']]=material_library.read(project_root,tid,meta)
    # All script sources are included: callbacks often share globals/functions.
    # Named object references are preserved by exporting the linked objects/scene.
    atlas=None
    if fragment.get('materialAtlas'):
        raw=material_atlas.read_project(project_root,fragment['materialAtlas']);files['textures/atlas.png']=raw
    elif fragment.get('useForgeAtlas'):
        raw=(Path(resources)/'web/forge-atlas.png').read_bytes();files['textures/forge-atlas.png']=raw;atlas=digest(raw)
    root=Path(project_root)
    documents=list(root.iterdir())+list((root/'package-docs').rglob('*'))
    for path in sorted(documents):
        if path.is_file() and (path.name=='README.md' or 'LICENSE' in path.name.upper()) and re.fullmatch(r'[A-Za-z0-9 _.-]{1,80}',path.name):
            raw=path.read_bytes()
            if len(raw)>1024*1024:raise ValueError('A package license/readme exceeds 1 MiB')
            name=path.name if path.parent==root else digest(str(path.relative_to(root)).encode())[:8]+'_'+path.name[:65]
            files['docs/'+name]=raw
    validate(fragment)
    extended=any(len(a['clips'])>16 or a['frames']>1000 for a in fragment['assets'].values())
    modern=bool(mids or any(e.get('engine') for e in entities) or any(a.get('format')==2 for a in fragment['assets'].values()))
    manifest=dict(format=FORMAT,version=1,name=title,minimumEngine=('0.9.4' if fragment['worldSectors'].get('format',1)>=4 else '0.9.3' if fragment['worldSectors'].get('format',1)>=2 else '0.9.2') if fragment.get('worldSectors') else ('0.9.0' if modern else ('0.8.2' if extended else ('0.8.0' if fragment.get('materialAtlas') else '0.7.0'))),project=encode_project(fragment),
                  atlasSha256=atlas,files={n:digest(raw) for n,raw in files.items()})
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf8')
    if len(files)>72 or sum(map(len,files.values()))>LIMIT:raise ValueError('Package exceeds the size/file budget')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for filename,raw in files.items():archive.writestr(filename,raw)
    return output.getvalue(),title+'.forgepack'

def inspect_package(raw,resources):
    if not raw or len(raw)>100*1024*1024:raise ValueError('Package is empty or too large')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries=archive.infolist();names=[e.filename for e in entries]
            if len(entries)>72 or len(names)!=len(set(names)):raise ValueError('Duplicate entries or too many package files')
            if sum(e.file_size for e in entries)>LIMIT:raise ValueError('Unpacked package exceeds 96 MiB')
            for entry in entries:
                name=entry.filename
                allowed=(name in ('manifest.json','world/world.fws') or re.fullmatch(r'assets/[a-f0-9]{12}\.iyam',name) or re.fullmatch(r'textures/[a-f0-9]{12}\.png',name) or name in ('textures/forge-atlas.png','textures/atlas.png') or re.fullmatch(r'docs/[A-Za-z0-9 _.-]{1,80}',name))
                if not allowed or entry.is_dir() or entry.flag_bits&1:raise ValueError('Unsupported package entry')
                if name.startswith('docs/') and (Path(name).name in ('.','..') or entry.file_size>1024*1024):raise ValueError('Invalid package document')
                if name.startswith('docs/') and (Path(name).name.endswith((' ','.')) or re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',Path(name).name.split('.')[0],re.I)):raise ValueError('Unsupported document filename')
                if name=='manifest.json' and entry.file_size>8*1024*1024:raise ValueError('Manifest is too large')
            manifest=json.loads(archive.read('manifest.json'))
            if not isinstance(manifest,dict):raise ValueError('Invalid manifest')
            if manifest.get('format')!=FORMAT or type(manifest.get('version')) is not int or manifest['version']!=1:raise ValueError('Unsupported Forge package version')
            hashes=manifest.get('files')
            if not isinstance(hashes,dict) or set(hashes)!=(set(names)-{'manifest.json'}):raise ValueError('Package file list does not match manifest')
            files={}
            for name,expected in hashes.items():
                data=archive.read(name)
                if digest(data)!=expected:raise ValueError('Package checksum mismatch: '+name)
                files[name]=data
    except (zipfile.BadZipFile,KeyError,UnicodeError,json.JSONDecodeError) as error:
        raise ValueError('Invalid Forge package') from error
    p=validate(manifest['project'])
    if p.get('worldSectors'):
        import world_sectors
        data=files.get('world/world.fws',b'');meta=p['worldSectors'];info=world_sectors.inspect(data)
        if info['format']!=meta.get('format',1)or digest(data)!=meta['sha256']or any(info[k]!=meta[k]for k in ['bytes','models','instances','cells']):raise ValueError('World resource metadata mismatch')
    elif 'world/world.fws'in files:raise ValueError('Unreferenced world resource')
    if p.get('nativeProject') or len(p['scenes'])!=1:raise ValueError('A package must contain one standard scene fragment')
    required={'assets/'+aid+'.iyam' for aid in p['assets']}
    if required!={n for n in files if n.startswith('assets/')}:raise ValueError('Package assets are incomplete')
    for aid,asset in p['assets'].items():asset.update(asset_info(files['assets/'+aid+'.iyam']))
    validate(p)
    required_textures={'textures/'+t['file'] for t in p.get('textures',{}).values()}
    if required_textures!={n for n in files if re.fullmatch(r'textures/[a-f0-9]{12}\.png',n)}:raise ValueError('Package material textures are incomplete')
    for tid,meta in p.get('textures',{}).items():
        data=files['textures/'+meta['file']]
        if digest(data)!=meta['sha256']:raise ValueError('Texture metadata checksum mismatch')
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            if image.format!='PNG' or image.size!=(meta['size'],meta['size']):raise ValueError('Invalid package texture dimensions')
            image.verify()
    if p.get('materialAtlas'):
        if 'textures/atlas.png' not in files:raise ValueError('The project material atlas is missing')
        material_atlas.validate_bytes(files['textures/atlas.png'],p['materialAtlas'])
    elif p.get('useForgeAtlas'):
        atlas=files.get('textures/forge-atlas.png')
        if not atlas or digest(atlas)!=manifest.get('atlasSha256') or digest(atlas)!=digest((Path(resources)/'web/forge-atlas.png').read_bytes()):
            raise ValueError('This package requires a matching Forge material atlas. Use the same engine materials/version as its author.')
    title=manifest.get('name')
    if not isinstance(title,str) or not 1<=len(title)<=60:raise ValueError('Invalid package name')
    return dict(project=p,files=files,name=title)

def summary(bundle):
    p=bundle['project']
    return dict(name=bundle['name'],objects=len(p['scenes'][0]['entities']),models=len(p['assets']),scripts=list(p['scripts']),
                clips=sum(len(a['clips']) for a in p['assets'].values()),bytes=sum(map(len,bundle['files'].values())),hasAtlas=bool(p.get('useForgeAtlas')))

def merge_package(bundle,target=None):
    source=bundle['project'];fresh=target is None
    if source.get('worldSectors')and not fresh:raise ValueError('Open streamed world packages as a new project')
    p=new_project(bundle['name']) if fresh else copy.deepcopy(validate(target))
    if p.get('nativeProject'):raise ValueError('Import packages into a standard scene project')
    custom=source.get('materialAtlas');existing_atlas=p.get('materialAtlas')
    if custom:
        if not fresh and ((existing_atlas and existing_atlas['sha256']!=custom['sha256']) or (p.get('useForgeAtlas') and not existing_atlas)):
            raise ValueError('The projects use different material atlases. Open this package as a new project.')
        p['materialAtlas']=copy.deepcopy(custom)
    elif source.get('useForgeAtlas') and existing_atlas:
        raise ValueError('A built-in atlas package cannot share a different project atlas. Open as a new project.')
    if fresh:
        p.update(camera=copy.deepcopy(source['camera']),background=source['background'],scripts={},assets={})
        p['scenes']=[dict(name=bundle['name'],entities=[])]
        for key in ('crosshair','runtimeHud'):
            if key in source:p[key]=source[key]
    conflicts=[name for name,code in source['scripts'].items() if name in p['scripts'] and p['scripts'][name]!=code]
    if conflicts:raise ValueError('Different scripts already use these names: '+', '.join(conflicts)+'. Open the package as a new project, or rename the conflicting scripts first.')
    existing={e['name'] for s in p['scenes'] for e in s['entities']}
    incoming=source['scenes'][0]['entities']
    names=[e['name'] for e in incoming if e['name'] in existing]
    if names:raise ValueError('Objects already use these names: '+', '.join(sorted(set(names)))+'. Open as a new project to preserve script references.')
    p['scripts'].update(copy.deepcopy(source['scripts']));remap={};new_files={}
    for old,asset in source['assets'].items():
        aid=uuid.uuid4().hex[:12]
        while aid in p['assets']:aid=uuid.uuid4().hex[:12]
        remap[old]=aid;value=copy.deepcopy(asset);value.update(id=aid,file=aid+'.iyam');p['assets'][aid]=value
        new_files[aid+'.iyam']=bundle['files']['assets/'+old+'.iyam']
    ids={e['id'] for s in p['scenes'] for e in s['entities']}
    texture_remap={tid:uuid.uuid4().hex[:12] for tid in source.get('textures',{})};material_remap={mid:uuid.uuid4().hex[:12] for mid in source.get('materials',{})}
    for tid,t in source.get('textures',{}).items():
        new=texture_remap[tid];meta=copy.deepcopy(t);meta['file']=new+'.png';p.setdefault('textures',{})[new]=meta;new_files['textures/'+new+'.png']=bundle['files']['textures/'+t['file']]
    for mid,m in source.get('materials',{}).items():
        material=copy.deepcopy(m);material['texture']=texture_remap.get(material['texture'],'');p.setdefault('materials',{})[material_remap[mid]]=material
    for aid in remap.values():
        if 'defaultMaterials' in p['assets'][aid]:p['assets'][aid]['defaultMaterials']=[material_remap.get(mid,'') for mid in p['assets'][aid]['defaultMaterials']]
    entity_remap={e['id']:uuid.uuid4().hex[:12] for e in incoming}
    for item in incoming:
        e=copy.deepcopy(item);e['id']=entity_remap[item['id']]
        while e['id'] in ids:e['id']=uuid.uuid4().hex[:12]
        ids.add(e['id'])
        if e['kind']=='model':e['asset']=remap[e['asset']]
        if 'materials' in e:e['materials']=[material_remap.get(mid,'') for mid in e['materials']]
        for component in e.get('engine',{}).values():
            if component.get('target'):component['target']=entity_remap[component['target']]
        for level in e.get('engine',{}).get('LOD',{}).get('levels',[]):level['asset']=remap[level['asset']]
        p['scenes'][p['activeScene']]['entities'].append(e)
    if source.get('worldSectors'):
        p['worldSectors']=copy.deepcopy(source['worldSectors']);p['worldSectors']['target']=entity_remap[p['worldSectors']['target']];new_files['world/world.fws']=bundle['files']['world/world.fws']
    if source.get('useForgeAtlas'):p['useForgeAtlas']=True
    # Validate merged budgets and references before the caller writes any files.
    p=validate(p)
    return p,new_files
