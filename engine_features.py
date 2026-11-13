"""Declarative editor components, shared validation and C++ generation."""
import copy,math,re
SCHEMA={
 'CharacterController':dict(walkSpeed=1.7,runSpeed=3.,sprintSpeed=5.2,jumpSpeed=4.5,height=1.8,crouchHeight=1.2,radius=.3,firstPerson=True),
 'Health':dict(maxHealth=100.,hideOnDeath=False),
 'Weapon':dict(damage=20.,range=40.,fireRate=6.,magazine=24.,reloadTime=2.),
 'CameraFollow':dict(target='',distance=3.,eyeHeight=1.62,crouchEyeHeight=1.05,offsetX=.35,allowToggle=True,firstPerson=False,hideTarget=True),
 'Trigger':dict(target='',radius=1.5,once=False,event='TriggerEnter'),
 'Interactable':dict(target='',radius=2.,event='Interact',hideOnUse=False),
 'NavigationAgent':dict(speed=2.,radius=.35,goal=[0,0,0],cellSize=1.,gridSize=64.,repathInterval=.5),
 'NPC':dict(target='',detectionRange=10.,attackRange=2.,damage=10.,attackInterval=1.,patrol=[]),
 'Attachment':dict(target='',bone='',offset=[0,0,0],rotation=[0,0,0],scale=[1,1,1],inheritVisibility=True),
 'Animator':dict(initial='',states=[],transitions=[],parameters={'Speed':0.},events=[]),
 'LOD':dict(levels=[],maxDistance=1000.),
 'Profiler':dict(enabled=True),
}
def finite(x,minimum=-10000,maximum=10000):return type(x) in (int,float) and math.isfinite(x) and minimum<=x<=maximum
def vector(v,minimum=-10000):return isinstance(v,list) and len(v)==3 and all(finite(x,minimum) for x in v)
def validate(p):
 entities={e['id']:e for s in p['scenes'] for e in s['entities']};scenes={e['id']:i for i,s in enumerate(p['scenes']) for e in s['entities']}
 for e in entities.values():
  components=e.get('engine',{})
  if not isinstance(components,dict) or set(components)-SCHEMA.keys():raise ValueError(e['name']+': unsupported engine component')
  slots=e.get('materials',[])
  if not isinstance(slots,list) or len(slots)>64 or any(x and x not in p.get('materials',{}) for x in slots):raise ValueError(e['name']+': invalid material slots')
  for kind,c in components.items():
   prefix=e['name']+' / '+kind+': '
   if not isinstance(c,dict) or set(c)-SCHEMA[kind].keys():raise ValueError(prefix+'invalid properties')
   for k,default in SCHEMA[kind].items():
    if k not in c:continue
    v=c[k]
    if type(default) is bool and type(v) is not bool:raise ValueError(prefix+k+' must be a checkbox')
    if type(default) is float and not finite(v,0,10000):raise ValueError(prefix+k+' must be a non-negative finite number')
    if isinstance(default,str) and (not isinstance(v,str) or len(v)>60):raise ValueError(prefix+k+' must be short text')
    if k in ('goal','offset','rotation','scale') and not vector(v,.001 if k=='scale' else -10000):raise ValueError(prefix+'invalid '+k)
   if kind in ('CharacterController','Health','Weapon','NavigationAgent'):
    for k in ('height','crouchHeight','radius','maxHealth','fireRate','magazine','reloadTime','cellSize','repathInterval'):
     if k in c and c[k]<=0:raise ValueError(prefix+k+' must be positive')
   if kind=='CharacterController' and c.get('crouchHeight',1.2)>c.get('height',1.8):raise ValueError(prefix+'crouch height exceeds standing height')
   if kind=='NavigationAgent' and (not 4<=c.get('gridSize',64)<=64 or c.get('gridSize',64)%1):raise ValueError(prefix+'grid size must be 4–64 cells')
   if c.get('target'):
    if c['target'] not in entities or scenes[c['target']]!=scenes[e['id']]:raise ValueError(prefix+'target must be in the same scene')
   if kind=='Attachment':
    target=entities.get(c.get('target'));bones=p['assets'].get(target.get('asset') if target else '',{}).get('bones',[])
    if not target or target is e or c.get('bone') not in [b['name'] for b in bones]:raise ValueError(prefix+'select a skeletal target and an existing bone')
    if max(target['scale'])-min(target['scale'])>.0001:raise ValueError(prefix+'bone attachments require a uniform target scale')
   if kind=='NPC':
    if not isinstance(c.get('patrol',[]),list) or len(c.get('patrol',[]))>64 or not all(vector(v) for v in c.get('patrol',[])):raise ValueError(prefix+'invalid patrol points')
    if 'NavigationAgent' not in components:raise ValueError(prefix+'add NavigationAgent for movement')
   if kind=='Animator':validate_animator(c,p['assets'].get(e.get('asset'),{}),prefix)
   if kind=='LOD':
    levels=c.get('levels',[])
    if not isinstance(levels,list) or not 1<=len(levels)<=4:raise ValueError(prefix+'use 1–4 LOD levels')
    last=-1
    for level in levels:
     if not isinstance(level,dict) or set(level)!={'asset','distance'} or level['asset'] not in p['assets'] or not finite(level['distance'],0) or level['distance']<=last:raise ValueError(prefix+'distances must increase and reference existing assets')
     last=level['distance']
     required={s['clip'] for s in components.get('Animator',{}).get('states',[])} or {e.get('clip','Idle')}
     if not required<={x['name'] for x in p['assets'][level['asset']]['clips']}:raise ValueError(prefix+'LOD is missing animation clips used by this object')
     base=p['assets'][e['asset']].get('bones',[]);other=p['assets'][level['asset']].get('bones',[])
     if [(b['name'],b['parent']) for b in base]!=[(b['name'],b['parent']) for b in other]:raise ValueError(prefix+'LOD must preserve the base skeleton names and hierarchy')
  visited=set();current=e
  while current.get('engine',{}).get('Attachment'):
   if current['id'] in visited:raise ValueError(e['name']+': cyclic bone attachment')
   visited.add(current['id']);current=entities[current['engine']['Attachment']['target']]
 return p

def validate_animator(c,asset,prefix):
 states=c.get('states',[]);transitions=c.get('transitions',[]);events=c.get('events',[]);clips={x['name']:x for x in asset.get('clips',[])}
 if not isinstance(states,list) or not 1<=len(states)<=32:raise ValueError(prefix+'add 1–32 animation states')
 names=set()
 for state in states:
  if not isinstance(state,dict) or set(state)!={'name','clip'} or not isinstance(state['name'],str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9 _-]{0,30}',state['name']) or state['name'] in names or state['clip'] not in clips:raise ValueError(prefix+'invalid/duplicate state or missing clip')
  names.add(state['name'])
 if c.get('initial') not in names:raise ValueError(prefix+'select an initial state')
 params=c.get('parameters',{})
 if not isinstance(params,dict) or len(params)>32 or any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,30}',k) or not finite(v) for k,v in params.items()):raise ValueError(prefix+'invalid animator parameters')
 if not isinstance(transitions,list) or len(transitions)>128:raise ValueError(prefix+'too many transitions')
 for t in transitions:
  if not isinstance(t,dict) or set(t)!={'from','to','parameter','operator','value','blend'} or t['from'] not in names|{'*'} or t['to'] not in names or t['parameter'] not in params or t['operator'] not in ('>','>=','<','<=','==','!=') or not finite(t['value']) or not finite(t['blend'],0,5):raise ValueError(prefix+'invalid transition')
 if not isinstance(events,list) or len(events)>256:raise ValueError(prefix+'too many events')
 for v in events:
  if not isinstance(v,dict) or set(v)!={'state','time','name'} or v['state'] not in names or not finite(v['time'],0) or not isinstance(v['name'],str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,30}',v['name']):raise ValueError(prefix+'invalid animation event')
  clip=clips[next(s['clip'] for s in states if s['name']==v['state'])]
  if v['time']>clip['count']/clip['fps']:raise ValueError(prefix+'event time exceeds clip duration')

def generate(e,p,cpp_string,num,vec):
 lines=[]
 for kind,config in e.get('engine',{}).items():
  c=copy.deepcopy(SCHEMA[kind]);c.update(config);prefix='entities.back().features['+cpp_string(kind)+']'
  for k,v in c.items():
   if k in ('states','transitions','parameters','events','patrol','levels'):continue
   if type(v) in (bool,int,float):lines.append(prefix+'.numbers['+cpp_string(k)+']='+num(v)+';')
   elif isinstance(v,str):lines.append(prefix+'.strings['+cpp_string(k)+']='+cpp_string(v)+';')
   elif isinstance(v,list):lines.append(prefix+'.vectors['+cpp_string(k)+']='+vec(v)+';')
  for point in c.get('patrol',[]):lines.append(prefix+'.points.push_back('+vec(point)+');')
  for level in c.get('levels',[]):lines.append(prefix+'.lods.push_back(forge::LODLevel('+num(level['distance'])+','+cpp_string('assets/'+level['asset']+'.iyam')+'));')
  for state in c.get('states',[]):lines.append(prefix+'.states.push_back(forge::AnimationState('+cpp_string(state['name'])+','+cpp_string(state['clip'])+'));')
  for t in c.get('transitions',[]):lines.append(prefix+'.transitions.push_back(forge::AnimationTransition('+','.join(cpp_string(t[k]) for k in ('from','to','parameter','operator'))+','+num(t['value'])+','+num(t['blend'])+'));')
  for name,value in c.get('parameters',{}).items():lines.append('entities.back().parameters['+cpp_string(name)+']='+num(value)+';')
  for event in c.get('events',[]):
   clip=next(s['clip'] for s in c['states'] if s['name']==event['state']);lines.append('entities.back().animationEvents.push_back(forge::ClipEvent('+cpp_string(clip)+','+num(event['time'])+','+cpp_string(event['name'])+'));')
 if e['kind']=='model':
  a=p['assets'][e['asset']]
  for c in a['clips']:lines.append('entities.back().clipInfo['+cpp_string(c['name'])+']=forge::ClipInfo('+num((c['count'] if c['loop'] else max(1,c['count']-1))/c['fps'])+','+str(c['loop']).lower()+');')
  for event in a.get('events',[]):lines.append('entities.back().animationEvents.push_back(forge::ClipEvent('+cpp_string(event['clip'])+','+num(event['time'])+','+cpp_string(event['name'])+'));')
 return lines
