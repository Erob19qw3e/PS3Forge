"""Project validation and deterministic native-scene generation."""
import copy, json, math, re, struct, uuid
from pathlib import Path
from project_format import decode_project, entity_scripts
from material_atlas import validate_metadata

IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,39}$')
PID = re.compile(r'^[a-f0-9]{12}$')

SCRIPTS = {
 'Spin': '#include "Forge.h"\nvoid Spin(forge::Entity& e, const forge::Input&, float dt) {\n    e.rotation.y += 45.0f * dt;\n}\n',
 'Player': '#include "Forge.h"\nvoid Player(forge::Entity& e, const forge::Input& input, float dt) {\n    e.position.x += input.moveX * 3.5f * dt;\n    e.position.z -= input.moveY * 3.5f * dt;\n    e.rotation.y += input.lookX * 120.0f * dt;\n    bool moving = fabsf(input.moveX) + fabsf(input.moveY) > 0.1f;\n    e.play(moving ? "Walk" : "Idle");\n    if (input.cross && e.grounded) e.velocity.y = 5.5f;\n}\n'
}

def entity(name='Cube', kind='cube', **kw):
    e = dict(id=uuid.uuid4().hex[:12], name=name, kind=kind, position=[0, .5, 0], rotation=[0,0,0], scale=[1,1,1], color=[.3,.65,.85], asset='', clip='Idle', script='', collider=False, gravity=False)
    e.update(kw)
    return e

def new_project(title='My PS3 Game'):
    pid = uuid.uuid4().hex[:12]
    return dict(id=pid,title=title,appid='P3'+pid[:7].upper(),version='01.00',activeScene=0,
                camera=dict(position=[7,6,10],target=[0,1,0]), background='#182634',
                scripts=copy.deepcopy(SCRIPTS),assets={},scenes=[dict(name='Main Scene',entities=[entity('Ground',scale=[20,.2,20],position=[0,-.1,0],color=[.25,.28,.3],collider=True),entity('Spinning Cube',script='Spin')])])

def validate(p):
    p = decode_project(p)
    if not isinstance(p,dict) or not PID.fullmatch(str(p.get('id',''))): raise ValueError('Invalid project ID')
    if not re.fullmatch(r'P3[A-Z0-9]{7}',p.get('appid','')): raise ValueError('TITLE_ID: P3 followed by 7 uppercase letters or digits')
    if not re.fullmatch(r'[0-9]{2}\.[0-9]{2}',p.get('version','')): raise ValueError('Version: use format 01.00')
    if not isinstance(p.get('title'),str) or not 1<=len(p['title'])<=60: raise ValueError('Invalid title')
    if not isinstance(p.get('scenes'),list) or not 1<=len(p['scenes'])<=8: raise ValueError('Between 1 and 8 scenes are supported')
    if not isinstance(p.get('activeScene'),int) or not 0<=p['activeScene']<len(p['scenes']): raise ValueError('Invalid active scene')
    def vector(v,scale=False):
        if not isinstance(v,list) or len(v)!=3 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or abs(x)>10000 or (scale and x<.001) for x in v): raise ValueError('Invalid transform')
    vector(p['camera']['position']); vector(p['camera']['target'])
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',p.get('background','')): raise ValueError('Invalid background color')
    if type(p.get('useForgeAtlas',False)) is not bool or type(p.get('crosshair',False)) is not bool: raise ValueError('Invalid rendering options')
    if 'materialAtlas' in p:
        validate_metadata(p['materialAtlas'])
        if not p.get('useForgeAtlas'):raise ValueError('Enable atlas rendering for a project material atlas')
    if not isinstance(p.get('runtimeHud',''),str) or len(p.get('runtimeHud',''))>1024: raise ValueError('HUD text is too long')
    scripts=p.get('scripts',{}); assets=p.get('assets',{})
    if not isinstance(scripts,dict) or len(scripts)>32 or any(not IDENT.fullmatch(n) or n.lower() in ('main','forge','project','rsxutil','debugfont','debugfont_renderer','forge_generated') or not isinstance(s,str) or len(s)>100000 for n,s in scripts.items()): raise ValueError('Invalid scripts: avoid reserved names such as main, Forge and project')
    if not isinstance(assets,dict) or len(assets)>32: raise ValueError('Up to 32 assets are supported')
    from material_library import validate as validate_materials
    validate_materials(p)
    for aid,a in assets.items():
        if not PID.fullmatch(aid) or a.get('file')!=aid+'.iyam': raise ValueError('Invalid asset reference')
        if type(a.get('usesForgeAtlas',False)) is not bool:raise ValueError('Invalid asset texture option')
    ids=set(); total=0; vertex_instances=0
    for scene in p['scenes']:
        if not isinstance(scene.get('name'),str) or len(scene['name'])>60: raise ValueError('Invalid scene name')
        for e in scene.get('entities',[]):
            total+=1
            if e.get('id') in ids or not PID.fullmatch(str(e.get('id',''))): raise ValueError('Duplicate or invalid object ID')
            ids.add(e['id'])
            if e.get('kind') not in ('cube','model'): raise ValueError('Unsupported object type')
            if type(e.get('visible',True)) is not bool or e.get('renderLayer','world') not in ('world','viewmodel'):raise ValueError('Invalid render layer or visibility')
            if not isinstance(e.get('name'),str) or len(e['name'])>60: raise ValueError('Invalid object name')
            for key in ('position','rotation','color'): vector(e[key])
            vector(e['scale'],True)
            if any(x<0 or x>1 for x in e['color']): raise ValueError('Color is out of range')
            for attachment in entity_scripts(e):
                if attachment['name'] not in scripts: raise ValueError('Missing script: '+attachment['name'])
            values=e.get('scriptValues',{})
            if not isinstance(values,dict) or len(values)>16:raise ValueError('Invalid script variables')
            for script,fields in values.items():
                if script not in scripts or not isinstance(fields,dict) or len(fields)>32:raise ValueError('Invalid script variable scope')
                for name,value in fields.items():
                    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,39}',name):raise ValueError('Invalid script variable name')
                    if not isinstance(value,(int,float,bool)) or not math.isfinite(value) or abs(value)>1000000:raise ValueError('Invalid script variable value')
            if e['kind']=='model':
                if e['asset'] not in assets: raise ValueError('Missing model')
                a=assets[e['asset']]
                if e['clip'] not in [c['name'] for c in a['clips']]: raise ValueError('Missing animation')
                vertex_instances+=max([a['vertices']]+[assets[level['asset']]['vertices'] for level in e.get('engine',{}).get('LOD',{}).get('levels',[]) if level.get('asset') in assets])
    if total>128 or vertex_instances>64000: raise ValueError('Budget: 128 objects and 64,000 animated vertices across all scenes')
    if sum(a['bytes'] for a in assets.values())>80*1024*1024: raise ValueError('Pose budget: up to 80 MiB per project')
    import world_sectors
    world_sectors.validate(p)
    from engine_features import validate as validate_features
    return validate_features(p)

def asset_info(data):
    if len(data)<32: raise ValueError('Truncated model file')
    if struct.unpack_from('>I',data,4)[0]==2:
        from skeletal_asset import inspect
        return inspect(data)
    magic,version,nv,ni,ng,nc,nf,stride=struct.unpack_from('>8I',data)
    if magic!=0x4959414d or version!=1 or not 0<nv<=20000 or not 0<ni<=1000000 or ni%3 or not 0<ng<=64 or not 0<nc<=128 or not 0<nf<=4096 or stride!=32: raise ValueError('Invalid IYAM format')
    expected=32+ng*24+nc*48+ni*2+nv*nf*32
    if expected!=len(data) or nv*nf*32>64*1024*1024: raise ValueError('Invalid model dimensions')
    clips=[];offset=32+ng*24
    for i in range(nc):
        name,first,count,fps,loop=struct.unpack_from('>32sIIfI',data,offset);offset+=48
        if b'\0' not in name or not count or first+count>nf or not math.isfinite(fps) or not 0<fps<=120: raise ValueError('Invalid clip')
        clips.append(dict(name=name.split(b'\0')[0].decode('utf8'),first=first,count=count,fps=fps,loop=bool(loop)))
    for i in range(ng):
        start,count,r,g,b,tint=struct.unpack_from('>II3fI',data,32+i*24)
        if start+count>ni or count%3 or tint>1 or any(not math.isfinite(c) or not 0<=c<=1 for c in (r,g,b)): raise ValueError('Invalid material')
    index_start=32+ng*24+nc*48
    if any(i[0]>=nv for i in struct.iter_unpack('>H',data[index_start:index_start+ni*2])): raise ValueError('Invalid model index')
    values=struct.iter_unpack('>8f',data[index_start+ni*2:])
    if any(any(not math.isfinite(f) for f in v) or any(abs(f)>100 for f in v[:3]) or any(abs(f)>2 for f in v[3:6]) for v in values): raise ValueError('Invalid vertices')
    return dict(vertices=nv,triangles=ni//3,frames=nf,clips=clips,bytes=len(data))

def obj_to_iyam(text):
    positions=[];triangles=[]
    for line in text.splitlines():
        parts=line.split()
        if not parts: continue
        if parts[0]=='v':
            v=tuple(float(x) for x in parts[1:4])
            if len(v)!=3 or any(not math.isfinite(x) or abs(x)>100 for x in v): raise ValueError('OBJ coordinates: 100 unit limit; resize the model before importing')
            positions.append(v)
        elif parts[0]=='f':
            ids=[]
            for item in parts[1:]:
                n=int(item.split('/')[0]); n=n-1 if n>0 else len(positions)+n
                if not 0<=n<len(positions): raise ValueError('Invalid OBJ index')
                ids.append(n)
            if len(ids)>256: raise ValueError('OBJ polygon is too large')
            for j in range(1,len(ids)-1): triangles.append((ids[0],ids[j],ids[j+1]))
    if not triangles or len(triangles)*3>20000: raise ValueError('OBJ is empty or exceeds 6,666 triangles (flat import)')
    vertices=[]
    for t in triangles:
        a,b,c=[positions[i] for i in t];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];length=math.sqrt(sum(x*x for x in n))
        if length<1e-10: continue
        n=[x/length for x in n]
        vertices.extend(struct.pack('>8f',*p,*n,.5,.5) for p in (a,b,c))
    count=len(vertices)
    if not count: raise ValueError('OBJ has no valid triangles')
    return struct.pack('>8I',0x4959414d,1,count,count,1,1,1,32)+struct.pack('>II3fI',0,count,.7,.7,.7,0)+struct.pack('>32sIIfI',b'Idle',0,1,24,1)+struct.pack('>'+str(count)+'H',*range(count))+b''.join(vertices)

def cpp_string(s): return json.dumps(s.encode('ascii','replace').decode(),ensure_ascii=True)
def num(x): return ('%.8g'%float(x))+('f' if '.' in ('%.8g'%float(x)) or 'e' in ('%.8g'%float(x)) else '.0f')
def vec(v): return 'forge::Vec3('+','.join(num(x) for x in v)+')'

def generate_scene(p,root):
    p=validate(p);root=Path(root); (root/'source/scripts').mkdir(parents=True,exist_ok=True)
    for name,code in p['scripts'].items(): (root/'source/scripts'/(name+'.cpp')).write_text(code,encoding='utf8')
    declarations=['#include "Forge.h"']
    declarations += ['void '+n+'(forge::Entity&,const forge::Input&,float);' for n in p['scripts']]
    dispatch={}
    for scene in p['scenes']:
        for e in scene['entities']:
            names=[item['name'] for item in entity_scripts(e) if item['enabled']]
            if len(names)>1:
                dispatch[e['id']]='forge_generated::entity_'+e['id']
                declarations+=['namespace forge_generated { static void entity_'+e['id']+'(forge::Entity& e,const forge::Input& input,float dt) {']
                declarations+=['::'+name+'(e,input,dt);' for name in names]
                declarations+=['} }']
            else: dispatch[e['id']]='::'+names[0] if names else 'nullptr'
    lines=declarations+['const char* forge::rootPath='+cpp_string('/dev_hdd0/game/'+p['appid']+'/USRDIR/')+';', 'void forge::createProject(){','sceneNames.clear(); entities.clear();']
    for scene in p['scenes']:lines.append('sceneNames.push_back('+cpp_string(scene['name'])+');')
    for si,scene in enumerate(p['scenes']):
        for e in scene['entities']:
            asset='assets/'+e['asset']+'.iyam' if e['kind']=='model' else ''
            lines+=['{ forge::Entity e;', 'e.name='+cpp_string(e['name'])+';e.scene='+str(si)+';',
                    'e.position='+vec(e['position'])+';e.rotation='+vec(e['rotation'])+';e.scale='+vec(e['scale'])+';e.color='+vec(e['color'])+';',
                    'e.asset='+cpp_string(asset)+';e.animation='+cpp_string(e['clip'])+';',
                    'e.collider='+str(bool(e['collider'])).lower()+';e.gravity='+str(bool(e['gravity'])).lower()+';',
                    'e.script='+dispatch[e['id']]+'; entities.push_back(e); }']
            lines+=['entities.back().id='+cpp_string(e['id'])+';entities.back().scriptLabel='+cpp_string(', '.join(item['name'] for item in entity_scripts(e) if item['enabled']))+';']
            if 'visible' in e or 'renderLayer' in e:
                lines+=['entities.back().visible='+str(e.get('visible',True)).lower()+';entities.back().viewModel='+str(e.get('renderLayer')=='viewmodel').lower()+';']
            if e['kind']=='model':lines+=['entities.back().textureAtlas='+str(p['assets'][e['asset']].get('usesForgeAtlas',False)).lower()+';']
            from material_library import native_indices
            _,bindings=native_indices(p)
            for mid in e.get('materials',[]):lines+=['entities.back().materials.push_back(forge::MaterialBinding('+str(bindings[mid])+','+vec(p['materials'][mid]['color'])+'));'] if mid else ['entities.back().materials.push_back(forge::MaterialBinding(-2));']
            for script,fields in e.get('scriptValues',{}).items():
                for name,value in fields.items():lines+=['entities.back().scriptValues['+cpp_string(script+'.'+name)+']='+num(value)+';']
            from engine_features import generate
            lines+=generate(e,p,cpp_string,num,vec)
            aids=[e['asset']] if e['kind']=='model' else []
            aids.extend(x['asset'] for x in e.get('engine',{}).get('LOD',{}).get('levels',[]))
            if aids:lines+=['entities.back().meshCapacity='+str(max(p['assets'][a]['vertices'] for a in aids))+';entities.back().indexCapacity='+str(max(p['assets'][a]['triangles']*3 for a in aids))+';']
            render_policy=p.get('worldSectors',{}).get('renderPolicy')
            if render_policy:
                radius=e.get('scriptValues',{}).get(render_policy,{}).get('radius',0)
                if radius>0:lines+=['entities.back().renderRadius='+num(radius)+';']
    if p.get('worldSectors'):
        w=p['worldSectors'];world_scene=next(i for i,s in enumerate(p['scenes'])if any(e['id']==w['target']for e in s['entities']));lines+=['worldSettings.scene='+str(world_scene)+';worldSettings.file="world/world.fws";worldSettings.target='+cpp_string(w['target'])+';worldSettings.radius='+num(w['radius'])+';worldSettings.vertexBudget='+str(w['vertexBudget'])+';worldSettings.maxModels='+str(w['maxModels'])+';worldSettings.maxDraws='+str(w['maxDraws'])+';worldSettings.cacheBytes='+str(w['cacheBytes'])+';']
        if 'collisionRadius' in w:lines+=['worldSettings.collisionRadius='+num(w['collisionRadius'])+';']
        if 'renderPolicy' in w:lines+=['worldSettings.renderPolicy=::'+w['renderPolicy']+';']
    lines+=['cameraPosition='+vec(p['camera']['position'])+'; cameraTarget='+vec(p['camera']['target'])+';',
            'activeScene='+str(p['activeScene'])+';', 'background=0xff'+p['background'][1:]+';',
            'useAtlas='+str(p.get('useForgeAtlas',False)).lower()+';crosshair='+str(p.get('crosshair',False)).lower()+';hudText='+cpp_string(p.get('runtimeHud',''))+';',
            'showProfiler='+str(any(e.get('engine',{}).get('Profiler',{}).get('enabled',False) for s in p['scenes'] for e in s['entities'])).lower()+';', '}']
    (root/'source/project.cpp').write_text('\n'.join(lines),encoding='utf8')
