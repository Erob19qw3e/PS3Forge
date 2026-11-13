import * as THREE from 'three';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const label=k=>k.replace(/([a-z])([A-Z])/g,'$1 $2').replace(/^./,c=>c.toUpperCase());
function select(value,choices,fn){const s=el('select');for(const [id,name] of choices){const o=el('option',name);o.value=id;s.append(o);}s.value=value;s.onchange=()=>fn(s.value);return s;}
function input(value,fn,type='text'){const i=el('input');i.type=type;if(type==='checkbox'){i.checked=!!value;i.onchange=()=>fn(i.checked);}else{i.value=value;i.onchange=()=>fn(type==='number'?Number(i.value):i.value);if(type==='number')i.step='.1';}return i;}
function field(name,control){const l=el('label',undefined,'field');l.append(el('span',name),control);control.setAttribute('aria-label',name);return l;}
function button(name,fn){const b=el('button',name);b.type='button';b.onclick=fn;return b;}
function vector(value,fn){const row=el('div',undefined,'vec');value.forEach((v,i)=>row.append(field('XYZ'[i],input(v,n=>{const copy=[...value];copy[i]=n;fn(copy);},'number'))));return row;}
function card(panel,title,remove){const c=el('section',undefined,'component-card');c.setAttribute('aria-label','Component '+title);const h=el('div',undefined,'component-heading');h.append(el('strong',title));if(remove)h.append(button('Remove',remove));c.append(h);panel.append(c);return c;}
export function defaultComponent(kind,e,p,schema){
 const c=structuredClone(schema[kind]);const entities=p.scenes[p.activeScene].entities;
 if('target'in c)c.target=entities.find(x=>x.id!==e.id&&x.engine?.CharacterController)?.id??entities.find(x=>x.id!==e.id)?.id??'';
 if(kind==='Attachment'){const target=entities.find(x=>x.id!==e.id&&p.assets[x.asset]?.bones?.length);c.target=target?.id??'';const bones=p.assets[target?.asset]?.bones??[];c.bone=bones.find(b=>/wrist.*ri|hand.*right|RightHand|hand_r$/i.test(b.name))?.name??bones[0]?.name??'';}
 if(kind==='LOD')c.levels=[{asset:e.asset,distance:0}];
 if(kind==='Animator'){
  const clips=p.assets[e.asset].clips.map(c=>c.name),idle=clips.find(c=>/^idle$/i.test(c))??clips[0],walk=clips.find(c=>/^walk(forward)?$/i.test(c)),run=clips.find(c=>/^run(forward)?$/i.test(c));
  c.states=[{name:'Idle',clip:idle}];if(walk)c.states.push({name:'Walk',clip:walk});if(run)c.states.push({name:'Run',clip:run});c.initial='Idle';c.transitions=[];
  for(let i=1;i<c.states.length;i++){const threshold=i===1?.05:2.1;c.transitions.push({from:c.states[i-1].name,to:c.states[i].name,parameter:'Speed',operator:'>',value:threshold,blend:.15},{from:c.states[i].name,to:c.states[i-1].name,parameter:'Speed',operator:'<=',value:threshold,blend:.15});}
 }
 return c;
}
function animatorUI(c,e,p,ctx,panel){
 const edit=(fn,rebuild=false)=>{ctx.edit(fn,rebuild);ctx.refresh();},states=()=>c.states.map(s=>[s.name,s.name]);
 panel.append(field('Initial state',select(c.initial,states(),v=>edit(()=>c.initial=v))));
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox',`0 0 280 ${Math.max(80,Math.ceil(c.states.length/2)*46+20)}`);svg.classList.add('animation-graph');
 const positions=new Map(c.states.map((s,i)=>[s.name,[65+(i%2)*145,25+Math.floor(i/2)*46]]));
 for(const t of c.transitions){const a=positions.get(t.from)??[5,5],b=positions.get(t.to);if(!b)continue;const line=document.createElementNS(svg.namespaceURI,'line');for(const [k,v] of Object.entries({x1:a[0],y1:a[1],x2:b[0],y2:b[1],stroke:'#7298ad','stroke-width':1.5}))line.setAttribute(k,v);svg.append(line);}
 for(const s of c.states){const [x,y]=positions.get(s.name),box=document.createElementNS(svg.namespaceURI,'rect'),text=document.createElementNS(svg.namespaceURI,'text');for(const [k,v]of Object.entries({x:x-50,y:y-13,width:100,height:26,rx:4,fill:s.name===c.initial?'#446b80':'#30383f',stroke:'#7fa2b4'}))box.setAttribute(k,v);text.setAttribute('x',x);text.setAttribute('y',y+4);text.setAttribute('text-anchor','middle');text.setAttribute('fill','#eef5fa');text.textContent=s.name;svg.append(box,text);}panel.append(svg);
 const clips=p.assets[e.asset].clips.map(c=>[c.name,c.name]);
 c.states.forEach((s,i)=>{const row=el('div',undefined,'engine-row');const rename=input(s.name,v=>edit(()=>{const old=s.name;s.name=v;if(c.initial===old)c.initial=v;for(const t of c.transitions){if(t.from===old)t.from=v;if(t.to===old)t.to=v;}for(const event of c.events)if(event.state===old)event.state=v;}));rename.setAttribute('aria-label','State name '+i);row.append(rename,select(s.clip,clips,v=>edit(()=>s.clip=v)),button('Remove',()=>{if(c.states.length<2)return;edit(()=>{c.states.splice(i,1);c.transitions=c.transitions.filter(t=>t.from!==s.name&&t.to!==s.name);c.events=c.events.filter(v=>v.state!==s.name);if(c.initial===s.name)c.initial=c.states[0].name;});}));panel.append(row);});
 panel.append(button('Add state',()=>edit(()=>c.states.push({name:'State'+c.states.length,clip:clips[0][0]}))));
 const params=el('details');params.append(el('summary','Parameters / preview defaults'));
 for(const [name,v]of Object.entries(c.parameters))params.append(field(name,input(v,value=>ctx.edit(()=>c.parameters[name]=value),'number')));
 params.append(button('Add parameter',()=>edit(()=>c.parameters['Parameter'+Object.keys(c.parameters).length]=0)));panel.append(params);
 const transitions=el('details');transitions.open=true;transitions.append(el('summary','Transitions'));
 c.transitions.forEach((t,i)=>{const row=el('div',undefined,'engine-subcard');row.append(field('From',select(t.from,[['*','Any state'],...states()],v=>edit(()=>t.from=v))),field('To',select(t.to,states(),v=>edit(()=>t.to=v))),field('Parameter',select(t.parameter,Object.keys(c.parameters).map(x=>[x,x]),v=>edit(()=>t.parameter=v))),field('Operator',select(t.operator,['>','>=','<','<=','==','!='].map(x=>[x,x]),v=>edit(()=>t.operator=v))),field('Value',input(t.value,v=>edit(()=>t.value=v),'number')),field('Blend seconds',input(t.blend,v=>edit(()=>t.blend=v),'number')),button('Remove transition',()=>edit(()=>c.transitions.splice(i,1))));transitions.append(row);});
 transitions.append(button('Add transition',()=>{if(c.states.length<2)return;edit(()=>c.transitions.push({from:c.states[0].name,to:c.states[1].name,parameter:Object.keys(c.parameters)[0],operator:'>',value:.1,blend:.15}));}));panel.append(transitions);
 const events=el('details');events.append(el('summary','Animation events'));
 c.events.forEach((event,i)=>{const row=el('div',undefined,'engine-subcard');row.append(field('State',select(event.state,states(),v=>edit(()=>event.state=v))),field('Time (seconds)',input(event.time,v=>edit(()=>event.time=v),'number')),field('Event name',input(event.name,v=>edit(()=>event.name=v))),button('Remove event',()=>edit(()=>c.events.splice(i,1))));events.append(row);});
 events.append(button('Add event',()=>edit(()=>c.events.push({state:c.states[0].name,time:.25,name:'Footstep'}))));panel.append(events);const status=el('p','Preview state: '+c.initial,'component-help');status.dataset.animatorPreview=e.id;panel.append(status);
}
export function renderEngineInspector(panel,e,ctx){
 const p=ctx.project,entities=p.scenes[p.activeScene].entities;
 if(p.assets[e.asset]?.bones?.length){const info=card(panel,'Skeleton');info.append(el('p',p.assets[e.asset].bones.length+' bones · CPU skinning · '+p.assets[e.asset].frames+' key frames','component-help'));info.append(button('Show / hide bones',()=>{const o=ctx.objects.get(e.id);if(o)o.userData.showBones=!o.userData.showBones;}));}
 for(const [kind,c]of Object.entries(e.engine??{})){
  const section=card(panel,label(kind),()=>{ctx.edit(()=>delete e.engine[kind]);ctx.refresh();});
  if(kind==='Animator'){animatorUI(c,e,p,ctx,section);continue;}
  if(kind==='LOD'){
   c.levels.forEach((level,i)=>{const row=el('div',undefined,'engine-subcard');row.append(field('Asset',select(level.asset,Object.values(p.assets).map(a=>[a.id,a.name]),v=>ctx.edit(()=>level.asset=v))),field('From distance',input(level.distance,v=>ctx.edit(()=>level.distance=v),'number')),button('Remove level',()=>{ctx.edit(()=>c.levels.splice(i,1));ctx.refresh();}));section.append(row);});
   section.append(button('Add LOD level',()=>{ctx.edit(()=>c.levels.push({asset:e.asset,distance:(c.levels.at(-1)?.distance??0)+10}));ctx.refresh();}),el('p','Lower-detail models load on first use in the native build. Keep matching clip names and skeletons.','component-help'));
  }
  for(const [key,defaultValue]of Object.entries(ctx.schema[kind])){
   if(key==='levels')continue;let control;const value=c[key]??defaultValue;
   const update=v=>ctx.edit(()=>c[key]=v);
   if(key==='target'){const candidates=entities.filter(x=>x.id!==e.id&&(kind!=='Attachment'||p.assets[x.asset]?.bones?.length));control=select(value,[['','Choose object…'],...candidates.map(x=>[x.id,x.name])],v=>{ctx.edit(()=>{c.target=v;if(kind==='Attachment')c.bone=p.assets[entities.find(x=>x.id===v)?.asset]?.bones?.[0]?.name??'';});ctx.refresh();});}
   else if(key==='bone'){const target=entities.find(x=>x.id===c.target);control=select(value,(p.assets[target?.asset]?.bones??[]).map(b=>[b.name,b.name]),update);}
   else if(key==='patrol'){
    const points=el('div');value.forEach((v,i)=>{const row=el('div',undefined,'engine-subcard');row.append(vector(v,n=>ctx.edit(()=>c.patrol[i]=n)),button('Remove point',()=>{ctx.edit(()=>c.patrol.splice(i,1));ctx.refresh();}));points.append(row);});points.append(button('Add patrol point',()=>{ctx.edit(()=>c.patrol.push([...e.position]));ctx.refresh();}));control=points;
   }else if(Array.isArray(defaultValue))control=vector(value,update);
   else control=input(value,update,typeof defaultValue==='boolean'?'checkbox':typeof defaultValue==='number'?'number':'text');
   section.append(field(label(key),control));
  }
  if(kind==='Attachment'){section.append(button('Attach to right hand',()=>{const target=entities.find(x=>x.id===c.target),bones=p.assets[target?.asset]?.bones??[];const bone=bones.find(b=>/wrist.*ri|hand.*right|RightHand|hand_r$/i.test(b.name));if(bone){ctx.edit(()=>c.bone=bone.name);ctx.refresh();}}),el('p','The target drives this transform. Adjust offset, rotation and scale here. Target scale must be uniform.','component-help'));const t=panel.querySelector('[aria-label="Component Transform"]');t?.querySelectorAll('input').forEach(i=>i.disabled=true);}
  if(kind==='NavigationAgent')section.append(button('Show / hide route preview',()=>{const o=ctx.objects.get(e.id);if(o)o.userData.showRoute=!o.userData.showRoute;}),el('p','Static grid preview; native NPC state appears in the profiler HUD.','component-help'));
 }
}
const textureCache=new Map();
function texture(url){if(!textureCache.has(url)){const t=new THREE.TextureLoader().load(url);t.flipY=false;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.colorSpace=THREE.SRGBColorSpace;textureCache.set(url,t);if(textureCache.size>32){const first=textureCache.keys().next().value;textureCache.get(first).dispose();textureCache.delete(first);}}return textureCache.get(url);}
export function applyMaterials(mesh,e,p){
 if(!e.materials?.some(Boolean))return;const count=mesh.userData.model?.groups.length??1,materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];
 for(let i=0;i<count;i++){const mid=e.materials[i],m=p.materials?.[mid];if(!m)continue;const t=p.textures?.[m.texture];const material=new THREE.MeshStandardMaterial({color:new THREE.Color(...m.color),map:t?texture('/texture/'+p.id+'/'+t.file+'?v='+t.sha256):null,alphaTest:m.alphaMode==='cutout'?m.alphaCutoff:0,roughness:.8,metalness:.08,side:THREE.DoubleSide});material.userData.forgeColor=[...m.color];materials[i]?.dispose();materials[i]=material;}
 mesh.material=count===1&&!mesh.userData.model?materials[0]:materials;
}
export function renderMaterialInspector(panel,e,ctx){
 const p=ctx.project,section=card(panel,'Material slots'),count=ctx.objects.get(e.id)?.userData.model?.groups.length??1;
 for(let i=0;i<count;i++)section.append(field('Slot '+(i+1),select(e.materials?.[i]??'',[['','Original material'],...Object.entries(p.materials??{}).map(([id,m])=>[id,m.name])],v=>{ctx.edit(()=>{e.materials??=[];while(e.materials.length<=i)e.materials.push('');e.materials[i]=v;},true);ctx.refresh();})));
 section.append(button('New material',()=>{const id=crypto.randomUUID().replaceAll('-','').slice(0,12);ctx.edit(()=>{p.materials??={};p.materials[id]={name:'Material '+(Object.keys(p.materials).length+1),color:[1,1,1],texture:'',alphaMode:'opaque',alphaCutoff:.5};e.materials??=[];e.materials[0]=id;},true);ctx.refresh();}));
 for(const mid of new Set((e.materials??[]).filter(Boolean))){const m=p.materials[mid];if(!m)continue;const sub=el('div',undefined,'engine-subcard');sub.append(field('Material name',input(m.name,v=>{ctx.edit(()=>m.name=v);ctx.refresh();})));const color=input('#'+new THREE.Color(...m.color).getHexString(THREE.LinearSRGBColorSpace),v=>ctx.edit(()=>m.color=new THREE.Color(v).convertLinearToSRGB().toArray(),true),'color');sub.append(field('Color',color));
  sub.append(field('Texture',select(m.texture,[['','No texture'],...Object.entries(p.textures??{}).map(([id,t])=>[id,t.name??t.file])],v=>ctx.edit(()=>m.texture=v,true))));
  const upload=input('',async()=>{} ,'file');upload.accept='image/png,image/jpeg,image/webp';upload.onchange=async()=>{const file=upload.files[0];if(!file)return;try{const response=await fetch('/api/texture/import',{method:'POST',headers:{'X-Forge-Token':ctx.token,'X-Project':p.id},body:file});const result=await response.json();if(!response.ok)throw Error(result.error);ctx.edit(()=>{p.textures??={};p.textures[result.id]={...result.metadata,name:file.name.slice(0,60)};m.texture=result.id;},true);ctx.refresh();}catch(error){ctx.fail(error);}};sub.append(field('Import texture',upload));
  sub.append(field('Opacity',select(m.alphaMode,[['opaque','Opaque'],['cutout','Cutout']],v=>{ctx.edit(()=>m.alphaMode=v,true);ctx.refresh();})));if(m.alphaMode==='cutout')sub.append(field('Alpha cutoff',input(m.alphaCutoff,v=>ctx.edit(()=>m.alphaCutoff=v,true),'number')));section.append(sub);
 }
}
const compare=(x,op,y)=>op==='>'?x>y:op==='>='?x>=y:op==='<'?x<y:op==='<='?x<=y:op==='=='?Math.abs(x-y)<1e-5:Math.abs(x-y)>=1e-5;
export function previewAnimator(e,o){
 const g=e.engine?.Animator;if(!g)return e.clip;let state=o.userData.animatorState??g.initial;
 if(!g.states.some(s=>s.name===state))state=g.initial;
 for(const t of g.transitions)if((t.from==='*'||t.from===state)&&t.to!==state&&compare(g.parameters[t.parameter]??0,t.operator,t.value)){state=t.to;o.userData.time=0;o.userData.blendDuration=t.blend;break;}
 o.userData.animatorState=state;const text=document.querySelector('[data-animator-preview="'+e.id+'"]');if(text)text.textContent='Preview state: '+state+(o.userData.lastEvent?' · Event: '+o.userData.lastEvent:'');return g.states.find(s=>s.name===state)?.clip??e.clip;
}
export function previewEvents(e,o,clip,time){
 const data=o.userData.model,events=(data.events??[]).filter(x=>data.clips[x.clip]?.name===clip.name).map(x=>({time:x.time,name:x.name}));for(const event of e.engine?.Animator?.events??[]){const state=e.engine.Animator.states.find(s=>s.name===event.state);if(state?.clip===clip.name)events.push(event);}
 const from=o.userData.eventClip===clip.name?(o.userData.eventTime??0):0,duration=(clip.loop?clip.count:Math.max(1,clip.count-1))/clip.fps;
 for(const event of events){const a=clip.loop?Math.floor(from/duration):0,b=clip.loop?Math.floor(time/duration):0;for(let n=a;n<=Math.min(b,a+16);n++)if(event.time+n*duration>from&&event.time+n*duration<=time)o.userData.lastEvent=event.name;}
 o.userData.eventClip=clip.name;o.userData.eventTime=time;
}
export function previewPath(e,p){
 const c=e.engine?.NavigationAgent;if(!c)return[];const size=c.gridSize??64,cell=c.cellSize??1,extent=size*cell/2,rad=c.radius??.35,goal=e.engine.NPC?.patrol?.[0]??c.goal??[0,0,0],entities=p.scenes[p.activeScene].entities;
 const index=(x,z)=>Math.max(0,Math.min(size-1,Math.floor((z+extent)/cell)))*size+Math.max(0,Math.min(size-1,Math.floor((x+extent)/cell)));
 const start=index(e.position[0],e.position[2]),finish=index(goal[0],goal[2]),blocked=new Uint8Array(size*size);for(let n=0;n<blocked.length;n++){const x=(n%size+.5)*cell-extent,z=(Math.floor(n/size)+.5)*cell-extent;for(const wall of entities)if(wall.id!==e.id&&wall.collider&&!wall.gravity&&wall.position[1]+wall.scale[1]/2>.2&&Math.abs(x-wall.position[0])<wall.scale[0]/2+rad&&Math.abs(z-wall.position[2])<wall.scale[2]/2+rad){blocked[n]=1;break;}}blocked[start]=0;
 const cost=new Float32Array(size*size).fill(Infinity),parent=new Int32Array(size*size).fill(-1),open=[start],closed=new Set();cost[start]=0;
 while(open.length){open.sort((a,b)=>(cost[b]+Math.abs(b%size-finish%size)+Math.abs(Math.floor(b/size)-Math.floor(finish/size)))-(cost[a]+Math.abs(a%size-finish%size)+Math.abs(Math.floor(a/size)-Math.floor(finish/size))));const n=open.pop();if(closed.has(n))continue;closed.add(n);if(n===finish)break;const x=n%size,z=Math.floor(n/size);for(const [dx,dz]of [[1,0],[-1,0],[0,1],[0,-1]]){const xx=x+dx,zz=z+dz,next=zz*size+xx;if(xx<0||xx>=size||zz<0||zz>=size||blocked[next]||cost[n]+1>=cost[next])continue;cost[next]=cost[n]+1;parent[next]=n;open.push(next);}}
 if(start!==finish&&parent[finish]<0)return[];const result=[];for(let n=finish;n!==start;n=parent[n])result.push([(n%size+.5)*cell-extent,e.position[1]+.05,(Math.floor(n/size)+.5)*cell-extent]);result.push([e.position[0],e.position[1]+.05,e.position[2]]);return result.reverse();
}
export function previewAttachments(p,objects){
 const entities=new Map(p.scenes[p.activeScene].entities.map(e=>[e.id,e])),done=new Set(),visiting=new Set();
 function attach(e){if(done.has(e.id))return;const a=e.engine?.Attachment,o=objects.get(e.id);if(!a||!o)return;if(visiting.has(e.id))return;visiting.add(e.id);const target=entities.get(a.target);if(target){attach(target);const parent=objects.get(target.id),bone=parent?.userData.bones?.get(a.bone);if(bone){parent.updateMatrixWorld(true);const offset=new THREE.Matrix4().compose(new THREE.Vector3(...a.offset),new THREE.Quaternion().setFromEuler(new THREE.Euler(...a.rotation.map(THREE.MathUtils.degToRad),'XYZ')),new THREE.Vector3(...a.scale));parent.matrixWorld.clone().multiply(bone).multiply(offset).decompose(o.position,o.quaternion,o.scale);if(a.inheritVisibility)o.visible=parent.visible;o.updateMatrixWorld(true);}}
 visiting.delete(e.id);done.add(e.id);}
 for(const e of entities.values())attach(e);
}
