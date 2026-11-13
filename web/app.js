import {WorldView} from './world-view.js';
import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {TransformControls} from './vendor/TransformControls.js';
import {parseIYAM,createMesh,sampleMesh} from './iyam.js';
import {decodeProject,encodeProject,entityScripts,setEntityScripts} from './project-format.js';
import {nameInitial} from './initials.js';
import {renderEngineInspector,renderMaterialInspector,defaultComponent,applyMaterials,previewAnimator,previewEvents} from './engine-ui.js';
import {installProfiler,updateEngineView,updateProfiler} from './engine-view.js';
import {scriptFields,scriptSource} from './script-api.js';
import {validScriptName,suggestedCopyName,duplicateSource,removeScript} from './script-actions.js';
import {openBlocks,isConvertibleScript,visualSourceForScript} from './visual-blocks.js';

const $=id=>document.getElementById(id);
let config,project,selected='',dirty=false,busy=false,lastBuild='',scriptName='',playing=true,scrubbing=false;
let undoStack=[],redoStack=[],gizmoSnapshot='',loadEpoch=0;
let selectedIds=new Set();
let engineSchema={},assetSignatures=null,assetPollBusy=false,draftTimer;
const cache=new Map(),objects=new Map();
const isNative=()=>project?.nativeProject==='block-garden-v1';
const scriptBank=()=>isNative()?project.nativeFiles:project.scripts;
const scriptLabel=name=>isNative()?name:name+'.cpp';
const nativeImage=new Image();nativeImage.alt='Last Block Garden screenshot from RPCS3';nativeImage.className='native-preview';

const viewport=$('viewport'),scene=new THREE.Scene();
const worldView=new WorldView(scene);let launchScene=null;
const viewScene=new THREE.Scene(),viewClones=new Map(),viewCamera=new THREE.PerspectiveCamera(65,16/9,.02,20);
viewScene.add(new THREE.HemisphereLight(0xc6e0f3,0x5c554c,2));const viewLight=new THREE.DirectionalLight(0xffedcf,2.5);viewLight.position.set(5,12,8);viewScene.add(viewLight);
const desktopMode=new URLSearchParams(location.search).has('desktop');if(desktopMode)document.body.classList.add('desktop-shell');
let gameMode=false;const gameCamera=new THREE.PerspectiveCamera(65,16/9,.2,1000);
const camera=new THREE.PerspectiveCamera(65,1,.05,2000);camera.position.set(7,6,10);
let renderer;
try{renderer=new THREE.WebGLRenderer({antialias:true});}catch(e){$('status').textContent='WebGL is not available in this browser';throw e;}
renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;viewport.appendChild(renderer.domElement);
const orbit=new OrbitControls(camera,renderer.domElement);orbit.target.set(0,1,0);orbit.enableDamping=true;
orbit.mouseButtons.MIDDLE=THREE.MOUSE.PAN;orbit.mouseButtons.RIGHT=null;
document.querySelector('.viewport-hint').textContent='Middle drag: pan · Shift + middle: orbit · Scroll: zoom · Right click: menu';
const grid=new THREE.GridHelper(40,40,0x4d7185,0x283b4d);scene.add(grid);
grid.position.y=.015;
scene.add(new THREE.HemisphereLight(0xc6e0f3,0x5c554c,2));
const previewRenderer=new THREE.WebGLRenderer({antialias:true});previewRenderer.setSize(320,180);previewRenderer.setPixelRatio(1);previewRenderer.outputColorSpace=THREE.SRGBColorSpace;$('cameraPreview').appendChild(previewRenderer.domElement);
const sun=new THREE.DirectionalLight(0xffedcf,2.5);sun.position.set(5,12,8);scene.add(sun);
const gizmo=new TransformControls(camera,renderer.domElement);scene.add(gizmo.getHelper());gizmo.setSize(.8);
const raycaster=new THREE.Raycaster(),pointer=new THREE.Vector2();
function resize(){const r=viewport.getBoundingClientRect(),width=Math.max(1,Math.round(r.width)),height=Math.max(1,Math.round(r.height));const size=renderer.getSize(new THREE.Vector2());if(size.x!==width||size.y!==height)renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();}
new ResizeObserver(resize).observe(viewport);
const freshId=()=>crypto.randomUUID().replaceAll('-','').slice(0,12);
function toast(text,error=false){$('toast').hidden=false;$('toast').textContent=text;$('toast').classList.toggle('error',error);clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,error?10000:4000);}
function status(text){$('status').textContent=text;}
async function api(path,data){if(data&&['save','build'].includes(path)){data=structuredClone(data);if(data.worldSectors&&data.id===project?.id&&launchScene!==null)data.activeScene=launchScene;data=encodeProject(data);}const opt=data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Forge-Token':config.token},body:JSON.stringify(data)};const r=await fetch('/api/'+path,opt);let value=await r.json();if(!r.ok){const e=Error(value.error||r.statusText);e.code=value.code;throw e;}if(value?.scenes)value=decodeProject(value);if(value?.project?.scenes)value.project=decodeProject(value.project);return value;}
function fail(e){toast(e.message||String(e),true);$('log').textContent+='\n'+(e.stack||e);status('Operation could not be completed');}
const nativeBlocked=new Set(['addCube','duplicate','remove','addScene','renameScene','deleteScene','newScript','captureCamera','undo','redo']);
function bind(id,fn){$(id).addEventListener('click',()=>Promise.resolve().then(()=>{if(document.body.classList.contains('home-screen')&&!['home','newProject'].includes(id))return;if(isNative()&&nativeBlocked.has(id))throw Error('Edit this voxel project through its C++ source files.');return fn();}).catch(fail));}
function snapshot(){return JSON.stringify(project);}
function remember(){if(!project)return;undoStack.push(snapshot());if(undoStack.length>80)undoStack.shift();redoStack=[];}
function mark(){clearTimeout(draftTimer);draftTimer=setTimeout(storeDraft,600);dirty=true;$('dirty').textContent='Unsaved changes';$('dirty').style.color='#dfbc7e';status('Unsaved changes · Ctrl+S to save');}
function clean(){clearTimeout(draftTimer);if(project)localStorage.removeItem('forge.draft.'+project.id);dirty=false;$('dirty').textContent='Saved';$('dirty').style.color='';status('Project saved locally');}
function activeScene(){return project.scenes[project.activeScene];}
function entity(){return activeScene().entities.find(e=>e.id===selected);}
function element(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
function option(value,label){const n=element('option','',label);n.value=value;return n;}
function showTab(name){document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));for(const id of ['assets','scripts','console'])$(id).classList.toggle('hidden',id!==name);}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
function mode(name){gizmo.setMode(name);document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===name));}
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>mode(b.dataset.mode));
gizmo.addEventListener('dragging-changed',ev=>{orbit.enabled=!ev.value;if(ev.value)gizmoSnapshot=snapshot();else if(gizmoSnapshot){undoStack.push(gizmoSnapshot);redoStack=[];gizmoSnapshot='';mark();renderInspector();}});
gizmo.addEventListener('objectChange',()=>{const e=entity(),o=gizmo.object;if(!gizmo.dragging||!e||!o)return;e.position=o.position.toArray();e.rotation=[o.rotation.x,o.rotation.y,o.rotation.z].map(THREE.MathUtils.radToDeg);e.scale=o.scale.toArray().map(v=>Math.max(.001,v));});
let down=null;
renderer.domElement.addEventListener('pointerdown',ev=>{if(ev.button===0)down=[ev.clientX,ev.clientY];});
renderer.domElement.addEventListener('pointerup',ev=>{if(!down||gizmo.dragging||gizmo.axis){down=null;return;}const distance=Math.hypot(ev.clientX-down[0],ev.clientY-down[1]);down=null;if(distance>5)return;const r=renderer.domElement.getBoundingClientRect();pointer.set((ev.clientX-r.left)/r.width*2-1,-(ev.clientY-r.top)/r.height*2+1);raycaster.setFromCamera(pointer,camera);const hits=raycaster.intersectObjects([...objects.values()],true);if(hits.length)select(hits[0].object.userData.entity);});

async function modelData(id){const key=project.id+'/'+id;if(!cache.has(key))cache.set(key,fetch('/asset/'+project.id+'/'+project.assets[id].file).then(r=>{if(!r.ok)throw Error('Model is unavailable');return r.arrayBuffer();}).then(parseIYAM));return cache.get(key);}
function disposeObject(o){o.geometry?.dispose();const mats=Array.isArray(o.material)?o.material:[o.material];mats.forEach(m=>m?.dispose());}
function applyTransform(o,e){o.position.fromArray(e.position);o.rotation.set(...e.rotation.map(THREE.MathUtils.degToRad),'XYZ');o.scale.fromArray(e.scale);o.visible=e.visible!==false;if(e.kind==='cube'){const c=o.material.userData.forgeColor??[1,1,1];o.material.color.setRGB(...e.color.map((v,i)=>v*c[i]));}}
async function renderScene(resetCamera=false){
 const epoch=++loadEpoch,staged=new Map();nativeWorkspace();renderAssets();updateSceneList();
 const discard=()=>{for(const o of staged.values())disposeObject(o);};
 for(const e of activeScene().entities){
  let mesh;
  if(e.kind==='cube')mesh=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({color:0xffffff,roughness:.75}));
  else{try{const data=await modelData(e.asset);if(epoch!==loadEpoch){discard();return;}const atlasUrl=project.materialAtlas?'/texture/'+project.id+'/atlas.png?v='+project.materialAtlas.sha256:'/forge-atlas.png';mesh=createMesh(data,!!project.assets[e.asset].usesForgeAtlas,atlasUrl);sampleMesh(mesh,e.clip,0,e.color);}catch(error){discard();fail(error);return;}}
  mesh.userData.entity=e.id;mesh.userData.clip=e.clip;applyMaterials(mesh,e,project);applyTransform(mesh,e);staged.set(e.id,mesh);
 }
 if(epoch!==loadEpoch){discard();return;}
 // Commit only after every mesh is ready: no empty/partial frames during loads.
 gizmo.detach();for(const o of viewClones.values())viewScene.remove(o);viewClones.clear();for(const o of objects.values()){scene.remove(o);disposeObject(o);}objects.clear();
 for(const e of activeScene().entities){const mesh=staged.get(e.id);scene.add(mesh);objects.set(e.id,mesh);if(e.renderLayer==='viewmodel'){const clone=mesh.clone();viewScene.add(clone);viewClones.set(e.id,clone);}}
 scene.background=new THREE.Color(project.background);
 if(resetCamera){camera.position.fromArray(project.camera.position);orbit.target.fromArray(project.camera.target);orbit.update();}
 selectedIds=new Set([...selectedIds].filter(id=>objects.has(id)));renderTree();renderInspector();renderAssets();renderScripts();updateSceneList();select(selected||activeScene().entities[0]?.id||'',false,true);updateBudget();
}
function updateSceneList(){const list=$('scenes');list.replaceChildren(...project.scenes.map((s,i)=>option(i,s.name)));list.value=project.activeScene;}
function renderTree(){if(isNative()){renderNativeTree();return;}const tree=$('tree');tree.replaceChildren();$('objectCount').textContent=activeScene().entities.length+' OBJECTS';for(const e of activeScene().entities){const row=element('div','tree-item'+(selectedIds.has(e.id)?' selected':''));row.dataset.entity=e.id;row.setAttribute('role','button');row.tabIndex=0;row.setAttribute('aria-label',e.name);row.setAttribute('aria-pressed',selectedIds.has(e.id));row.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();select(e.id,ev.ctrlKey||ev.metaKey);}};const initial=element('span','name-initial',nameInitial(e.name));initial.setAttribute('aria-hidden','true');row.append(initial,element('span','object-name',e.name));row.onclick=ev=>select(e.id,ev.ctrlKey||ev.metaKey);tree.append(row);}}
function select(id,additive=false,keep=false){if(additive){if(selectedIds.has(id))selectedIds.delete(id);else selectedIds.add(id);selected=selectedIds.has(id)?id:[...selectedIds].at(-1)||'';}else{selected=id;if(!keep||!selectedIds.has(id))selectedIds=new Set(id?[id]:[]);}const o=objects.get(selected);if(o&&!entity()?.engine?.Attachment)gizmo.attach(o);else gizmo.detach();renderTree();renderInspector();}
function field(label,input){const wrap=element('label','field');wrap.append(element('span','',label),input);return wrap;}
function inputText(value,change,type='text'){const i=element('input');i.type=type;i.value=value;i.onchange=()=>change(i.value);return i;}
function dropdown(value,choices,change){const s=element('select');choices.forEach(([v,n])=>s.append(option(v,n)));s.value=value;s.onchange=()=>change(s.value);return s;}
function change(fn,rebuild=false){if(busy){toast('Wait for the current operation to finish',true);return;}remember();fn();mark();if(rebuild)renderScene().catch(fail);else{const e=entity(),o=objects.get(selected);if(e&&o)applyTransform(o,e);renderTree();updateBudget();}}
function componentCard(panel,title,remove){
 const card=element('section','component-card'),head=element('div','component-heading');
 card.setAttribute('aria-label','Component '+title);head.append(element('strong','',title));
 if(remove){const button=element('button','component-remove','Remove');button.type='button';button.setAttribute('aria-label','Remove component '+title);button.disabled=busy;button.onclick=()=>{change(remove);renderInspector();};head.append(button);}
 card.append(head);panel.append(card);return card;
}
function renderInspector(){
 const panel=$('inspector');panel.replaceChildren();if(isNative()){panel.append(element('div','section-label','Block Garden · C++ / RSX'),element('p','empty','Voxel world: 64 × 32 × 64. Edit world generation and movement in include/voxel.h; rendering and input in source/main.cpp.'),element('p','empty','Edit C++ source files, save and choose Build PS3. Run in RPCS3 launches the latest compiled build.'),element('p','empty','The viewport shows a recorded RPCS3 screenshot. Player saves are stored separately.'));return;}const e=entity();if(!e){panel.append(element('p','empty','Select an object in the scene.'));return;}
 panel.append(field('Name',inputText(e.name,v=>change(()=>e.name=v.slice(0,60)))));
 const transform=componentCard(panel,'Transform');
 for(const [key,title] of [['position','Position'],['rotation','Rotation · degrees'],['scale','Scale']]){
  const row=element('div','vec');['X','Y','Z'].forEach((axis,index)=>{const label=element('label');label.append(element('span','',axis));const i=inputText(Number(e[key][index].toFixed(3)),v=>{const f=Number(v);if(!Number.isFinite(f)||Math.abs(f)>10000||(key==='scale'&&f<.001)){toast('Value is out of range',true);renderInspector();return;}change(()=>e[key][index]=f);},'number');i.step=key==='rotation'?'5':'.1';i.setAttribute('aria-label',title+' '+axis);label.append(i);row.append(label);});transform.append(field(title,row));
 }
 const mesh=componentCard(panel,'Mesh & Material');
 const visibility=element('input');visibility.type='checkbox';visibility.checked=e.visible!==false;visibility.setAttribute('aria-label','Visible');visibility.onchange=()=>change(()=>e.visible=visibility.checked);const visibleLabel=element('label','check');visibleLabel.append(visibility,document.createTextNode('Visible'));mesh.append(visibleLabel);
 mesh.append(field('Layer',dropdown(e.renderLayer||'world',[['world','World'],['viewmodel','First-person weapon']],v=>change(()=>e.renderLayer=v,true))));
 const color=element('input');color.type='color';color.value='#'+new THREE.Color(...e.color).getHexString(THREE.LinearSRGBColorSpace);color.onchange=()=>change(()=>e.color=new THREE.Color(color.value).convertLinearToSRGB().toArray());mesh.append(field(e.kind==='model'?'Tint':'Color',color));
 if(e.kind==='model'){
  mesh.append(field('Asset',dropdown(e.asset,Object.values(project.assets).map(a=>[a.id,a.name]),v=>change(()=>{e.asset=v;e.clip=project.assets[v].clips[0].name;},true))));
  const animator=componentCard(panel,'Animation');
  animator.append(field('Starting clip',dropdown(e.clip,project.assets[e.asset].clips.map(c=>[c.name,c.name]),v=>change(()=>{e.clip=v;const o=objects.get(e.id);if(o)o.userData.time=0;}))));
 }
 const attachments=entityScripts(e);
 attachments.forEach((attachment,index)=>{
  const update=fn=>{change(()=>{const items=structuredClone(entityScripts(e));fn(items);setEntityScripts(e,items);});renderInspector();};
  const card=componentCard(panel,'C++ Script',()=>{setEntityScripts(e,entityScripts(e).filter((_,i)=>i!==index));});
  const choices=Object.keys(scriptBank()).filter(n=>n===attachment.name||!attachments.some(a=>a.name===n));
  const selector=dropdown(attachment.name,choices.map(n=>[n,n]),v=>update(items=>items[index].name=v));selector.setAttribute('aria-label','Script '+(index+1));card.append(field('Script',selector));
  const enabled=element('input');enabled.type='checkbox';enabled.checked=attachment.enabled;enabled.disabled=busy;enabled.setAttribute('aria-label','Enable '+attachment.name);enabled.onchange=()=>update(items=>items[index].enabled=enabled.checked);
  const label=element('label','check');label.append(enabled,document.createTextNode('Enabled'));card.append(label);
  for(const spec of scriptFields(scriptBank()[attachment.name]||'')){
   const value=e.scriptValues?.[attachment.name]?.[spec.name]??spec.value;
   const edit=v=>{if(typeof v==='number'&&(!Number.isFinite(v)||Math.abs(v)>1000000)){toast('Value is out of range',true);return;}change(()=>{e.scriptValues??={};e.scriptValues[attachment.name]??={};e.scriptValues[attachment.name][spec.name]=v;});};
   let control;
   if(spec.type==='flag'){control=element('input');control.type='checkbox';control.checked=!!value;control.onchange=()=>edit(control.checked);}
   else{control=inputText(value,v=>edit(Number(v)),'number');control.step='any';}
   control.disabled=busy;control.setAttribute('aria-label',attachment.name+' '+spec.name);card.append(field(spec.name,control));
  }
  if(scriptFields(scriptBank()[attachment.name]||'').length){const reset=element('button','','Reset variables');reset.disabled=busy;reset.onclick=()=>{change(()=>{if(e.scriptValues)delete e.scriptValues[attachment.name];});renderInspector();};card.append(reset);}
  const order=element('div','row');order.append(element('span','muted','Order '+(index+1)));
  for(const [title,offset] of [['Move up',-1],['Move down',1]]){const button=element('button','',title);button.disabled=busy||index+offset<0||index+offset>=attachments.length;button.setAttribute('aria-label',title+' '+attachment.name);button.onclick=()=>update(items=>{[items[index],items[index+offset]]=[items[index+offset],items[index]];});order.append(button);}card.append(order);
 });
 if(e.collider){const collider=componentCard(panel,'Box Collider',()=>e.collider=false);collider.append(element('p','component-help','Axis-aligned collision bounds follow the object scale. Rotation does not affect the bounds.'));}
 if(e.gravity){const body=componentCard(panel,'Rigid Body',()=>e.gravity=false);body.append(element('p','component-help','Gravity is enabled. Add a Box Collider to collide with static objects.'));}
 const engineContext={project,schema:engineSchema,objects,edit:change,refresh:renderInspector,token:config.token,fail};
 renderMaterialInspector(panel,e,engineContext);renderEngineInspector(panel,e,engineContext);
 const unusedScripts=Object.keys(scriptBank()).filter(n=>!attachments.some(a=>a.name===n));
 const engineChoices=Object.keys(engineSchema).filter(k=>!e.engine?.[k]&&(!['Animator','LOD'].includes(k)||e.kind==='model')).map(k=>['engine:'+k,k.replace(/([a-z])([A-Z])/g,'$1 $2')]);
 const available=[...engineChoices,...(!e.collider?[['collider','Box Collider']]:[]),...(!e.gravity?[['gravity','Rigid Body']]:[]),...(attachments.length<16&&unusedScripts.length?[['script','C++ Script']]:[])];
 const addRow=element('div','component-add');
 if(available.length){const chooser=dropdown('',[['','Choose a component…'],...available],()=>{});chooser.setAttribute('aria-label','Component to add');const add=element('button','','Add');add.disabled=busy;add.onclick=()=>{const kind=chooser.value;if(!kind)return;change(()=>{if(kind.startsWith('engine:')){const name=kind.slice(7);e.engine??={};if(name==='NPC'&&!e.engine.NavigationAgent)e.engine.NavigationAgent=defaultComponent('NavigationAgent',e,project,engineSchema);e.engine[name]=defaultComponent(name,e,project,engineSchema);}else if(kind==='script')setEntityScripts(e,[...entityScripts(e),{name:unusedScripts[0],enabled:true}]);else e[kind]=true;});renderInspector();};addRow.append(chooser,add);}
 else addRow.append(element('p','component-help','All available components have been added.'));
 panel.append(addRow);
 panel.append(element('p','empty','Physics and scripts run in the PS3 build. This viewport previews the scene and animations.'));
}
function renderAssets(){const list=$('assetGrid');list.replaceChildren();for(const a of Object.values(project.assets)){const card=element('div','asset-card');card.dataset.asset=a.id;card.append(element('div','asset-symbol',nameInitial(a.name)),element('strong','',a.name),element('small','',a.triangles.toLocaleString()+' triangles · '+a.clips.length+' clips'),element('small','',(a.bytes/1048576).toFixed(1)+(a.format===2?' MiB skeletal data':' MiB poses')));const add=element('button','','Add');add.title='Add to scene';add.onclick=ev=>{ev.stopPropagation();addAsset(a);};card.append(add);card.ondblclick=()=>addAsset(a);list.append(card);}const catalog=worldView.catalog();if(catalog.length){const section=element('section');section.style.cssText='width:100%;padding:8px';const title=element('strong','','Streamed world assets ('+catalog.length+')');const search=element('input');search.placeholder='Filter world assets';search.setAttribute('aria-label','Filter world assets');search.style.cssText='margin:8px;width:280px';const cards=element('div');cards.style.cssText='display:flex;flex-wrap:wrap';const draw=()=>{const query=search.value.toLowerCase();const matches=catalog.filter(a=>a.name.toLowerCase().includes(query)||String(a.id)===query);cards.replaceChildren();for(const a of matches.slice(0,80)){const card=element('div','asset-card');card.append(element('div','asset-symbol',nameInitial(a.name)),element('strong','',a.name),element('small','','World model '+a.id));const locate=element('button','','Locate');locate.disabled=!a.instance;locate.onclick=()=>worldView.locate(a,camera,orbit);card.append(locate);cards.append(card);}cards.append(element('p','muted',matches.length>80?'Showing 80 matches. Use the filter to find another asset.':matches.length+' matches'));};search.oninput=draw;section.append(title,search,cards);list.append(section);draw();}}
function addAsset(a){remember();const e={id:freshId(),name:a.name,kind:'model',position:[0,0,0],rotation:[0,0,0],scale:[1,1,1],color:[1,1,1],asset:a.id,clip:a.clips[0].name,script:'',collider:false,gravity:false};if(a.defaultMaterials)e.materials=[...a.defaultMaterials];activeScene().entities.push(e);selected=e.id;mark();renderScene().catch(fail);}
function renderScripts(){const list=$('scriptList');list.replaceChildren();for(const name of Object.keys(scriptBank())){const b=element('button',name===scriptName?'active':'',scriptLabel(name));b.dataset.script=name;b.onclick=()=>openScript(name);list.append(b);}if(scriptName&&!scriptBank()[scriptName])scriptName='';if(!scriptName)openScript(Object.keys(scriptBank())[0]||'');refreshVisualButtons();}
function openScript(name){if(scriptName&&$('code').value!==scriptBank()[scriptName]&&!confirm('Discard unsaved script changes?'))return;scriptName=name;$('scriptName').textContent=name?scriptLabel(name):'Select a script';$('code').value=scriptBank()[name]||'';for(const b of $('scriptList').children)b.classList.toggle('active',b.textContent===scriptLabel(name));refreshVisualButtons();}
function currentScriptText(name){return scriptName===name?$('code').value:scriptBank()[name];}
function rememberScriptDraft(){const draft=structuredClone(project);if(scriptName)draft.scripts[scriptName]=$('code').value;undoStack.push(JSON.stringify(draft));if(undoStack.length>80)undoStack.shift();redoStack=[];if(scriptName)scriptBank()[scriptName]=$('code').value;}
function duplicateEditorScript(name){
 if(isNative()||busy)return;
 if(Object.keys(scriptBank()).length>=32)throw Error('A project supports up to 32 scripts.');
 const copyName=prompt('Name for the duplicate script',suggestedCopyName(name,scriptBank()));if(!copyName)return;
 if(!validScriptName(copyName)||Object.hasOwn(scriptBank(),copyName))throw Error('Invalid script name or name already in use');
 const code=duplicateSource(currentScriptText(name),name,copyName);
 if(code.length>100000)throw Error('The duplicated script exceeds the source size limit.');
 rememberScriptDraft();scriptBank()[copyName]=code;mark();renderScripts();openScript(copyName);renderInspector();toast('Script duplicated: '+copyName);
}
function deleteEditorScript(name){
 if(isNative()||busy)return;
 rememberScriptDraft();const count=removeScript(project,name);
 if(scriptName===name){scriptName='';$('code').value='';}
 mark();renderScripts();renderInspector();toast('Script deleted'+(count?' · '+count+' attachments removed':'')+'. Undo restores it.');
}
async function copyEditorScript(name){
 const text=currentScriptText(name);if(typeof text!=='string')return;
 try{if(!navigator.clipboard?.writeText)throw Error('Use clipboard fallback');await navigator.clipboard.writeText(text);}
 catch(error){const previous=document.activeElement,selection=previous===$('code')?[$('code').selectionStart,$('code').selectionEnd]:null;const area=element('textarea');area.value=text;area.style.cssText='position:fixed;left:-9999px;top:0';document.body.append(area);area.select();let copied=false;try{copied=document.execCommand('copy');}finally{area.remove();previous?.focus();if(selection)$('code').setSelectionRange(...selection);}if(!copied)throw Error('Clipboard copy failed. Select the code and press Ctrl+C.');}
 toast('Script code copied');
}
function updateBudget(){if(isNative()){$('budget').textContent='Native voxel · C++ / PSL1GHT · RPCS3 screenshot';return;}const all=project.scenes.flatMap(s=>s.entities);const bytes=Object.values(project.assets).reduce((n,a)=>n+a.bytes,0);const tris=activeScene().entities.reduce((n,e)=>n+(e.kind==='cube'?12:project.assets[e.asset]?.triangles||0),0);$('budget').textContent=activeScene().entities.length+' objects · '+tris.toLocaleString()+' triangles · '+(bytes/1048576).toFixed(1)+' / 80 MiB asset data';}
async function refreshProjects(){config=await api('config');if(!Object.keys(engineSchema).length)engineSchema=await api('engine-schema');$('projects').replaceChildren(...config.projects.map(p=>option(p.id,p.title)));if(project)$('projects').value=project.id;renderStartProjects();}
function renderStartProjects(){
 const list=$('startProjectList'),query=$('projectSearch').value.trim().toLocaleLowerCase('en-US');list.replaceChildren();
 const projects=(config?.projects||[]).filter(p=>p.title.toLocaleLowerCase('en-US').includes(query));
 $('projectTotal').textContent=String(config?.projects.length||0);$('projectListEmpty').hidden=projects.length>0;
 $('projectListEmpty').textContent=config?.projects.length?'No projects match your search.':'No projects yet. Create your first one.';
 for(const p of projects){
  const card=element('button','start-project');card.type='button';card.disabled=busy||!!p.error;card.title=p.error??'';card.setAttribute('aria-label','Open '+p.title);
  const initial=element('span','project-initial',nameInitial(p.title));initial.setAttribute('aria-hidden','true');
  const info=element('span','project-info');info.append(element('strong','',p.title),element('small','',p.error?'Project JSON needs repair; other projects remain available':p.nativeProject?'Native C++ project':'3D scene project'));
  card.append(initial,info,element('span','project-open','Open'));card.onclick=()=>openFromStart(p.id).catch(startFail);list.append(card);
 }
 $('resumeProject').hidden=!project;
}
function startFail(e){$('startError').textContent=e.message||String(e);fail(e);}
function setStartVisible(visible){$('startScreen').hidden=!visible;document.body.classList.toggle('home-screen',visible);if(visible){renderStartProjects();status('Choose a project to get started');}else{resize();}}
async function showHome(){if(busy)throw Error('Wait for the current operation to finish');setStartVisible(true);await refreshProjects();$('projectSearch').focus();}
async function openFromStart(id){
 if(busy)return;if(dirty&&!confirm('Discard unsaved changes and open another project?'))return;
 $('startError').textContent='';setBusy(true);renderStartProjects();
 try{await loadProject(id);}finally{setBusy(false);renderStartProjects();}
}
$('projectSearch').oninput=renderStartProjects;
$('resumeProject').onclick=()=>{if(project)setStartVisible(false);};
$('createProjectForm').onsubmit=async ev=>{
 ev.preventDefault();if(busy)return;const title=$('projectTitle').value.trim();
 if(!title){$('startError').textContent='Enter a project name.';$('projectTitle').focus();return;}
 if(dirty&&!confirm('Discard unsaved changes and create a new project?'))return;
 $('startError').textContent='';setBusy(true);$('createProjectSubmit').disabled=true;renderStartProjects();
 try{const p=await api('new',{title});await refreshProjects();await loadProject(p.id);$('projectTitle').value='';}
 catch(e){startFail(e);}finally{setBusy(false);$('createProjectSubmit').disabled=false;renderStartProjects();}
};
bind('home',showHome);
async function loadProject(id){project=await api('project?id='+encodeURIComponent(id));launchScene=project.activeScene;const draft=localStorage.getItem('forge.draft.'+id);if(draft){try{const d=JSON.parse(draft);if(confirm('Recover unsaved changes for '+project.title+'?'))project=d.project;}catch(error){fail(error);}}assetSignatures=null;selected='';scriptName='';undoStack=[];redoStack=[];lastBuild='';$('download').classList.add('disabled');$('rpcs3').disabled=true;const recovered=!!draft&&JSON.stringify(project)!==JSON.stringify(await api('project?id='+encodeURIComponent(id)));if(recovered){dirty=true;$('dirty').textContent='Recovered unsaved changes';}else clean();if(project.worldSectors){const index=project.scenes.findIndex(s=>s.entities.some(e=>e.id===project.worldSectors.target));if(index>=0)project.activeScene=index;}renderAssets();await renderScene(true);status(project.worldSectors?'Loading streamed scenery…':'Project loaded');await worldView.load(project);worldView.update(project,orbit.target);renderAssets();status(worldView.state.ready?'Streamed scenery ready - '+worldView.state.instances+' visible objects':'Project loaded');$('projects').value=id;const b=await api('last-build?id='+id);if(b.job){lastBuild=b.job;$('download').href=b.download;$('download').download=project.title+'.pkg';$('download').classList.remove('disabled');$('rpcs3').disabled=false;}if(isNative()){showTab('scripts');status('Block Garden · native sources · F7 build · F6 run');}setStartVisible(false);}
async function save(){if(!project)return;if(scriptName&&$('code').value!==scriptBank()[scriptName]){remember();scriptBank()[scriptName]=$('code').value;}const editorScene=project.activeScene;project=await api('save',project);if(project.worldSectors)project.activeScene=editorScene;clean();await refreshProjects();}
function setBusy(value){busy=value;document.body.classList.toggle('busy',value);for(const id of ['build','newProject','addScene','addCube','duplicate','remove','save','newScript','saveScript','projects','scenes'])$(id).disabled=value;nativeWorkspace();refreshVisualButtons();if(project)renderInspector();}
async function waitJob(id){showTab('console');for(;;){const job=await api('job?id='+id);$('phase').textContent=job.phase;$('log').textContent=job.log||job.phase;$('log').parentElement.scrollTop=$('log').parentElement.scrollHeight;status(job.phase);if(job.status==='done')return job;if(job.status==='error'){const e=Error(job.error);e.code=job.code;throw e;}await new Promise(r=>setTimeout(r,600));}}
bind('save',save);
bind('newProject',async()=>{await showHome();$('projectTitle').focus();});
$('projects').onchange=async()=>{try{if(dirty&&!confirm('Discard your changes?')){$('projects').value=project.id;return;}await loadProject($('projects').value);}catch(e){fail(e);}};
$('scenes').onchange=()=>{if(!project.worldSectors)remember();project.activeScene=Number($('scenes').value);selected='';if(!project.worldSectors)mark();renderScene().catch(fail);};
bind('addScene',()=>{const name=prompt('Scene name','New Scene');if(!name)return;if(project.scenes.length>=8)throw Error('Up to eight scenes are supported');remember();project.scenes.push({name,entities:[]});project.activeScene=project.scenes.length-1;selected='';mark();return renderScene();});
bind('addCube',()=>{remember();const e={id:freshId(),name:'Cube',kind:'cube',position:[0,.5,0],rotation:[0,0,0],scale:[1,1,1],color:[.3,.65,.85],asset:'',clip:'Idle',script:'',collider:false,gravity:false};activeScene().entities.push(e);selected=e.id;mark();return renderScene();});
bind('duplicate',()=>{const e=entity();if(!e)return;remember();const copy=structuredClone(e);copy.id=freshId();copy.name+=' Copy';copy.position[0]+=1;activeScene().entities.push(copy);selected=copy.id;mark();return renderScene();});
bind('remove',()=>{if(!entity())return;remember();activeScene().entities=activeScene().entities.filter(e=>e.id!==selected);selected='';mark();return renderScene();});
bind('undo',()=>{if(!undoStack.length)return;redoStack.push(snapshot());project=JSON.parse(undoStack.pop());selected='';mark();return renderScene();});
bind('redo',()=>{if(!redoStack.length)return;undoStack.push(snapshot());project=JSON.parse(redoStack.pop());selected='';mark();return renderScene();});
bind('grid',()=>grid.visible=!grid.visible);
bind('captureCamera',()=>{remember();project.camera={position:camera.position.toArray(),target:orbit.target.toArray()};mark();toast('PS3 starting camera updated from the current view');});
bind('play',()=>{playing=!playing;$('play').textContent=playing?'Pause':'Play';});
$('timeline').onpointerdown=()=>scrubbing=true;window.addEventListener('pointerup',()=>scrubbing=false);
$('timeline').oninput=()=>{const o=objects.get(selected);if(o?.userData.model)o.userData.time=Number($('timeline').value);};
const scriptTemplate=dropdown('rotate',[['blank','Blank behavior'],['rotate','Rotating item'],['move','Move and jump'],['pickup','Health pickup']],()=>{});scriptTemplate.setAttribute('aria-label','Script template');$('newScript').before(scriptTemplate);
bind('newScript',()=>{const name=prompt('Script name (no spaces)','MyScript');if(!name)return;if(!/^[A-Za-z_][A-Za-z0-9_]{0,39}$/.test(name)||scriptBank()[name])throw Error('Invalid name or name already in use');remember();scriptBank()[name]=scriptSource(name,scriptTemplate.value);mark();scriptName='';renderScripts();openScript(name);showTab('scripts');renderInspector();});
const newVisualScript = element('button', '', 'New visual script');
newVisualScript.id = 'newVisualScript';
$('newScript').after(newVisualScript);
const editVisualScript = element('button', '', 'Edit blocks');
editVisualScript.id = 'editVisualScript';
$('saveScript').before(editVisualScript);

function refreshVisualButtons(){
 const blocked = !project || isNative() || busy;
 newVisualScript.hidden = blocked;
 editVisualScript.hidden = blocked || !scriptName || !($('code').value.startsWith('// PS3Forge Visual Blocks v1 ') || isConvertibleScript(scriptName,$('code').value));
}

function launchVisualScript(existing){
 if (!project || isNative() || busy) return;
 const currentProject = project;
 const target = activeScene().entities.find(entity => entity.id === selected);
 const source = existing ? visualSourceForScript(scriptName,$('code').value) : '';
 openBlocks({
  name: existing ? scriptName : (Object.hasOwn(scriptBank(), 'MyBehavior') ? suggestedCopyName('MyBehavior', scriptBank()) : 'MyBehavior'),
  source,
  apply(name, code){
   if (project !== currentProject || busy) throw Error('The project changed. Open Visual Blocks again.');
   if (!validScriptName(name) || (!existing && Object.hasOwn(scriptBank(), name))) throw Error('Choose an unused script name with letters, numbers or underscores.');
   if (!existing && Object.keys(scriptBank()).length >= 32) throw Error('A project supports up to 32 scripts.');
   if (!existing && target && entityScripts(target).length >= 16) throw Error('This object already has too many scripts. Select another object.');
   rememberScriptDraft();
   scriptBank()[name] = code;
   if (!existing && target) setEntityScripts(target, [...entityScripts(target), {name, enabled:true}]);
   scriptName = name;
   $('code').value = code;
   renderScripts();
   openScript(name);
   renderInspector();
   mark();
   toast(target && !existing ? 'Script attached. Save and build to try it.' : 'Blocks applied. Save and build to try them.');
  }
 });
}
bind('newVisualScript', () => launchVisualScript(false));
bind('editVisualScript', () => launchVisualScript(true));
$('code').addEventListener('input', refreshVisualButtons);
refreshVisualButtons();

bind('saveScript',async()=>{if(!scriptName)return;remember();scriptBank()[scriptName]=$('code').value;mark();await save();toast('Script saved. Build the project to run it on PS3.');});
$('code').addEventListener('keydown',ev=>{if(ev.key==='Tab'){ev.preventDefault();const n=$('code'),a=n.selectionStart,b=n.selectionEnd;n.setRangeText('    ',a,b,'end');}});
$('importFile').onchange=async()=>{const f=$('importFile').files[0];if(!f)return;try{setBusy(true);await save();const r=await fetch('/api/import',{method:'POST',headers:{'X-Forge-Token':config.token,'X-Project':project.id,'X-Filename':encodeURIComponent(f.name)},body:f});const d=await r.json();if(!r.ok)throw Error(d.error);const j=await waitJob(d.job);project=decodeProject(j.result.project);clean();await renderScene();showTab('assets');toast('Model imported. Choose Add on the asset to place it in your scene.');}catch(e){fail(e);}finally{setBusy(false);$('importFile').value='';}};
bind('build',async()=>{try{setBusy(true);if(!await ensureBuildTools())return;await save();const result=await api('build',project);const job=await waitJob(result.job);lastBuild=job.id;$('download').href=job.result.download;$('download').download=project.title+'.pkg';$('download').classList.remove('disabled');$('rpcs3').disabled=false;toast('PKG built and verified. You can now test it in RPCS3 or on your console.');}finally{setBusy(false);}});
bind('rpcs3',async()=>{if(!lastBuild)return;if(dirty&&!confirm('Run the latest build? Your current changes have not been compiled.'))return;await api('rpcs3',{job:lastBuild});toast('RPCS3 launch requested');});
bind('clearLog',()=>$('log').textContent='');
bind('settings',()=>{for(const key of Object.keys(config.settings))if($('settingsForm').elements[key])$('settingsForm').elements[key].value=config.settings[key];for(const key of ['title','appid','version'])$('settingsForm').elements[key].value=project[key];$('settingsForm').elements.password.value='';$('sshResult').textContent='';updateBuildFields();$('settingsDialog').showModal();});
bind('closeSettings',()=>$('settingsDialog').close());
async function saveSettings(){const form=$('settingsForm');const data={};for(const key of Object.keys(config.settings))data[key]=form.elements[key].value;if(form.elements.password.value)data.password=form.elements.password.value;await api('settings',data);config.settings={...data};delete config.settings.password;form.elements.password.value='';}
$('settingsForm').onsubmit=async ev=>{ev.preventDefault();try{await saveSettings();remember();for(const k of ['title','appid','version'])project[k]=$('settingsForm').elements[k].value;mark();await save();$('settingsDialog').close();toast('Settings saved');}catch(e){fail(e);}};
bind('sshTest',async()=>{await saveSettings();$('sshResult').textContent='Checking build tools…';try{const r=await api(config.settings.buildMode==='local'?'test-local':'test-ssh',{});$('sshResult').textContent=r.output;}catch(e){$('sshResult').textContent=e.message;}});
function focus(){const o=objects.get(selected);if(!o)return;const box=new THREE.Box3().setFromObject(o);const c=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3()).length();orbit.target.copy(c);camera.position.copy(c).add(new THREE.Vector3(1,.8,1.5).normalize().multiplyScalar(Math.max(3,size*1.8)));}
window.addEventListener('keydown',ev=>{if(document.body.classList.contains('home-screen'))return;if((ev.ctrlKey||ev.metaKey)&&ev.key.toLowerCase()==='s'){ev.preventDefault();save().catch(fail);return;}if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)||($('settingsDialog').open||$('sshLoginDialog').open))return;if(busy)return;if((ev.ctrlKey||ev.metaKey)&&ev.key==='z'){ev.preventDefault();$(ev.shiftKey?'redo':'undo').click();return;}if(ev.key==='Delete')$('remove').click();if(ev.key.toLowerCase()==='f')focus();if(ev.key.toLowerCase()==='w')mode('translate');if(ev.key.toLowerCase()==='e')mode('rotate');if(ev.key.toLowerCase()==='r')mode('scale');});
window.addEventListener('beforeunload',ev=>{if(dirty){ev.preventDefault();ev.returnValue='';}});

// Reusable object/scene bundles and the editor's compact right-click menu.
const packageInput=element('input');packageInput.type='file';packageInput.accept='.forgepack';packageInput.hidden=true;packageInput.id='packageInput';document.body.append(packageInput);
const packageDialog=element('dialog');packageDialog.id='packageDialog';packageDialog.setAttribute('aria-label','Import Forge package');
const packageTitle=element('h2','','Import Forge package'),packageInfo=element('p'),packageError=element('p','package-error'),packageActions=element('div','row');
const importCurrent=element('button','','Import into current project'),importNew=element('button','','Open as new project'),cancelPackage=element('button','','Cancel');
importCurrent.id='packageImportCurrent';importNew.id='packageImportNew';cancelPackage.onclick=()=>packageDialog.close();packageActions.append(importCurrent,importNew,cancelPackage);packageDialog.append(packageTitle,packageInfo,packageError,packageActions);document.body.append(packageDialog);
let incomingPackage=null;
function packageDraft(){const draft=structuredClone(project);if(scriptName&&!isNative())draft.scripts[scriptName]=$('code').value;return draft;}
async function exportForgePackage(kind='selection',assetId=''){
 if(busy||!project||isNative())return;
 const draft=packageDraft();let ids=kind==='scene'?activeScene().entities.map(e=>e.id):[...selectedIds];
 if(assetId){const a=draft.assets[assetId];const e={id:freshId(),name:a.name,kind:'model',asset:a.id,clip:a.clips[0].name,position:[0,0,0],rotation:[0,0,0],scale:[1,1,1],color:[1,1,1],script:'',collider:false,gravity:false};if(a.defaultMaterials)e.materials=[...a.defaultMaterials];draft.scenes[draft.activeScene].entities.push(e);ids=[e.id];}
 if(!ids.length){toast('Select objects to export',true);return;}
 setBusy(true);
 try{const result=await api('package/export',{project:encodeProject(draft),objects:ids});const link=element('a');link.href=result.download;link.download=result.filename;document.body.append(link);link.click();link.remove();toast('Package ready: '+result.filename);}
 finally{setBusy(false);}
}
packageInput.onchange=async()=>{
 const file=packageInput.files[0];if(!file)return;
 try{if(file.size>100*1024*1024)throw Error('Packages can be up to 100 MiB');setBusy(true);
  const response=await fetch('/api/package/inspect',{method:'POST',headers:{'X-Forge-Token':config.token},body:file});const info=await response.json();if(!response.ok)throw Error(info.error);
  incomingPackage=info;packageInfo.textContent=info.name+' · '+info.objects+' objects · '+info.models+' models · '+info.clips+' animation clips · '+info.scripts.length+' scripts. Editable C++ source is included. Use a scene package for objects linked by name.';
  packageError.textContent='';importCurrent.disabled=!project||isNative();packageDialog.showModal();
 }catch(error){fail(error);}finally{setBusy(false);packageInput.value='';}
};
async function importForgePackage(fresh){
 if(!incomingPackage||busy)return;
 if(fresh&&dirty){if(!confirm('Save the current project before opening this package? Cancel keeps your current work open.'))return;await save();}
 const draft=project?packageDraft():null;
 try{setBusy(true);packageError.textContent='';const result=await api('package/import',{upload:incomingPackage.upload,newProject:fresh,project:draft?encodeProject(draft):null});
  if(fresh){packageDialog.close();await refreshProjects();await loadProject(result.project.id);}
  else{undoStack.push(JSON.stringify(draft));redoStack=[];project=result.project;scriptName='';mark();await renderScene();packageDialog.close();}
  toast('Package imported. '+(fresh?'Project saved locally.':'Save to keep these objects.'));
 }catch(error){packageError.textContent=error.message||String(error);}finally{setBusy(false);}
}
importCurrent.onclick=()=>importForgePackage(false).catch(fail);importNew.onclick=()=>importForgePackage(true).catch(fail);
const contextMenu=element('div','forge-context');contextMenu.id='forgeContextMenu';contextMenu.hidden=true;contextMenu.setAttribute('role','menu');document.body.append(contextMenu);
const packageFileMenu=document.querySelector('.app-menu details>div');
for(const [label,action] of [['Import package…',()=>packageInput.click()],['Export selected package…',()=>exportForgePackage()]]){const button=element('button','',label);button.onclick=()=>{document.querySelectorAll('details[open]').forEach(d=>d.open=false);Promise.resolve().then(action).catch(fail);};packageFileMenu?.append(button);}
function closeContext(){contextMenu.hidden=true;}
function showContext(event,actions){
 event.preventDefault();contextMenu.replaceChildren();for(const [id,label,action,disabled=false] of actions){const button=element('button','',label);button.type='button';button.dataset.action=id;button.setAttribute('role','menuitem');button.disabled=disabled;button.onclick=()=>{closeContext();Promise.resolve().then(action).catch(fail);};contextMenu.append(button);}
 contextMenu.hidden=false;contextMenu.style.left=Math.max(8,Math.min(event.clientX,innerWidth-contextMenu.offsetWidth-8))+'px';contextMenu.style.top=Math.max(8,Math.min(event.clientY,innerHeight-contextMenu.offsetHeight-8))+'px';contextMenu.querySelector('button:not(:disabled)')?.focus();
}
document.addEventListener('contextmenu',event=>{
 if(event.target.closest('input,textarea,select'))return;
 if(!event.target.closest('.hierarchy,#viewport,#assets,#startScreen,#scriptList'))return;
 if(busy){event.preventDefault();return;}
 const scriptRow=event.target.closest('[data-script]');
 if(scriptRow){const name=scriptRow.dataset.script;showContext(event,[['script-copy','Copy code',()=>copyEditorScript(name)],['script-duplicate','Duplicate script…',()=>duplicateEditorScript(name),isNative()],['script-delete','Delete script',()=>deleteEditorScript(name),isNative()]]);return;}
 const row=event.target.closest('[data-entity]'),asset=event.target.closest('[data-asset]');if(row&&!selectedIds.has(row.dataset.entity))select(row.dataset.entity);
 if(event.target===renderer.domElement&&!gameMode){const r=renderer.domElement.getBoundingClientRect();pointer.set((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1);raycaster.setFromCamera(pointer,camera);const hit=raycaster.intersectObjects([...objects.values()],true).find(h=>h.object.visible);if(hit&&!selectedIds.has(hit.object.userData.entity))select(hit.object.userData.entity);}
 const actions=[['import-package','Import package…',()=>packageInput.click()]];
 if(project&&!isNative()){
  if(asset)actions.unshift(['export-asset','Export model package…',()=>exportForgePackage('selection',asset.dataset.asset)],['add-asset','Add model to scene',()=>addAsset(project.assets[asset.dataset.asset])]);
  else actions.unshift(['export-selection','Export selected ('+selectedIds.size+')…',()=>exportForgePackage(),!selectedIds.size],['export-scene','Export scene package…',()=>exportForgePackage('scene'),!activeScene().entities.length]);
  actions.push(['duplicate','Duplicate object',()=>$('duplicate').click(),!selected],['frame','Frame object',()=>focus(),!selected],['delete','Delete object',()=>$('remove').click(),!selected],['save','Save project',()=>save()],['undo','Undo',()=>$('undo').click(),!undoStack.length],['redo','Redo',()=>$('redo').click(),!redoStack.length]);
 }
 showContext(event,actions);
});
document.addEventListener('pointerdown',event=>{if(!contextMenu.contains(event.target))closeContext();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeContext();if(!contextMenu.hidden&&['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();const buttons=[...contextMenu.querySelectorAll('button:not(:disabled)')],index=buttons.indexOf(document.activeElement);buttons[(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}});
window.addEventListener('blur',closeContext);window.addEventListener('resize',closeContext);
installProfiler(viewport,document.querySelector('.viewport-tools'));
let lastTime=performance.now();
const blocksBackdropStyle = document.createElement('style');
blocksBackdropStyle.textContent = 'body:has(.forge-toolbox[open]) #viewport canvas, body:has(.forge-toolbox[open]) #cameraPreview canvas { visibility: hidden; }';
document.head.append(blocksBackdropStyle);
function animate(now){requestAnimationFrame(animate);const dt=Math.min(.05,(now-lastTime)/1000);lastTime=now;if(document.querySelector('.forge-toolbox[open]'))return;if(document.body.classList.contains('home-screen'))return;orbit.update();if(project){for(const e of activeScene().entities){const o=objects.get(e.id);if(!o?.userData.model)continue;if(playing&&!(scrubbing&&e.id===selected))o.userData.time+=dt;const effectiveClip=previewAnimator(e,o);const clip=sampleMesh(o,effectiveClip,o.userData.time,e.color);previewEvents(e,o,clip,o.userData.time);if(e.id===selected){const duration=(clip.loop?clip.count:clip.count-1)/clip.fps;$('clipLabel').textContent=clip.name;$('timeline').max=duration;if(!scrubbing)$('timeline').value=clip.loop?o.userData.time%duration:Math.min(duration,o.userData.time);$('timeLabel').textContent=Number($('timeline').value).toFixed(2)+' s';}}updateEngineView(project,objects,scene,camera,modelData,viewClones);worldView.update(project,orbit.target);}renderViews();if(project)updateProfiler(project,renderer,dt*1000);}
requestAnimationFrame(animate);
try{await refreshProjects();const requested=new URLSearchParams(location.search).get('project');if(requested){await loadProject(requested);status('Ready · '+project.title);}else setStartVisible(true);}catch(e){startFail(e);}

bind('showObjects',()=>document.querySelector('.hierarchy').classList.toggle('drawer'));
bind('showInspector',()=>document.querySelector('.inspector').classList.toggle('drawer'));

bind('saveCopy',async()=>{const title=prompt('Copy name',project.title+' Copy');if(!title)return;const draft=structuredClone(project);if(scriptName)draft.scripts[scriptName]=$('code').value;const result=await api('project/copy',{project:encodeProject(draft),title});await refreshProjects();await loadProject(result.project.id);toast('Independent project copy saved.');});
bind('exportProject',async()=>{await save();window.location.href='/api/export?id='+project.id;});
bind('renameScene',()=>{const name=prompt('Scene name',activeScene().name);if(!name)return;remember();activeScene().name=name.slice(0,60);mark();return renderScene();});
bind('deleteScene',()=>{if(project.scenes.length===1)throw Error('Keep at least one scene');if(!confirm('Delete this scene? You can restore it with Undo.'))return;remember();project.scenes.splice(project.activeScene,1);project.activeScene=0;selected='';mark();return renderScene();});

function updateGameCamera(){if(!project)return;gameCamera.position.fromArray(project.camera.position);gameCamera.lookAt(new THREE.Vector3(...project.camera.target));gameCamera.updateProjectionMatrix();}
function renderGameView(target,aspect){
 const hidden=[];
 for(const [id,clone] of viewClones){const original=objects.get(id);if(!original)continue;clone.position.copy(original.position);clone.rotation.copy(original.rotation);clone.scale.copy(original.scale);clone.visible=original.visible;hidden.push([original,original.visible]);original.visible=false;}
 gameCamera.aspect=aspect;gameCamera.updateProjectionMatrix();target.render(scene,gameCamera);target.clearDepth();viewCamera.aspect=aspect;viewCamera.updateProjectionMatrix();
 const clear=target.autoClear;target.autoClear=false;target.render(viewScene,viewCamera);target.autoClear=clear;
 for(const [object,visible] of hidden)object.visible=visible;
}
function renderViews(){
 if(document.body.classList.contains('home-screen'))return;
 if(isNative()){return;}
 if(!project){renderer.render(scene,camera);return;}updateGameCamera();
 const visible=gizmo.getHelper().visible,gridVisible=grid.visible;
 if(gameMode){gizmo.getHelper().visible=false;grid.visible=false;gameCamera.aspect=camera.aspect;gameCamera.updateProjectionMatrix();}
 if(gameMode)renderGameView(renderer,camera.aspect);else renderer.render(scene,camera);
 gizmo.getHelper().visible=false;grid.visible=false;renderGameView(previewRenderer,16/9);
 gizmo.getHelper().visible=visible;grid.visible=gridVisible;
}
function setView(game){gameMode=game;document.body.classList.toggle('game-mode',game);$('sceneView').classList.toggle('active',!game);$('gameView').classList.toggle('active',game);$('viewModeLabel').textContent=game?'Game camera · visual preview':'Perspective';orbit.enabled=!game;gizmo.enabled=!game;}
bind('sceneView',()=>setView(false));bind('gameView',()=>setView(true));
async function captureReview(){
 if(desktopMode){const r=await api('desktop/capture',{});toast('Capture requested: '+r.id);return;}
 renderViews();const a=document.createElement('a');a.download='forge-scene.png';a.href=renderer.domElement.toDataURL('image/png');a.click();toast('Scene exported. The desktop app can also capture the editor and project state.');
}
bind('captureReview',captureReview);
const commands={newProject:'newProject',save:'save',exportProject:'exportProject',settings:'settings',undo:'undo',redo:'redo',duplicate:'duplicate',remove:'remove',addCube:'addCube',build:'build',rpcs3:'rpcs3',captureReview:'captureReview',newScript:'newScript',addScene:'addScene'};
function command(name){if(name==='importPackage')return packageInput.click();if(name==='exportPackage')return exportForgePackage().catch(fail);if(name==='exportScenePackage')return exportForgePackage('scene').catch(fail);if(name==='home')return showHome();if(name==='newProject')return $('newProject').click();if(document.body.classList.contains('home-screen'))return;if((name==='undo'||name==='redo')&&document.activeElement===$('code'))return document.execCommand(name);if(name==='save')return save();if(name==='scene')return setView(false);if(name==='game')return setView(true);if(name==='importModel'){if(isNative())throw Error('Voxel assets are defined in the native source files.');return $('importFile').click();}if(name==='assets'||name==='scripts'||name==='console')return showTab(name);if(!commands[name])throw Error('Command is unavailable');$(commands[name]).click();}
document.querySelectorAll('[data-command]').forEach(b=>b.onclick=()=>{document.querySelectorAll('details[open]').forEach(d=>d.open=false);try{command(b.dataset.command);}catch(e){fail(e);}});
$('code').addEventListener('input',()=>{if(project)mark();});
window.ForgeDesktop={command,
 async openProject(id){try{if(busy||dirty)throw Error('Save your changes and wait for the current operation before opening another project');await refreshProjects();await loadProject(id);}catch(e){fail(e);}},
 state(){return {schema:'ps3forge.inspect.v1',timestamp:new Date().toISOString(),project:project?structuredClone(project):null,selected,dirty,busy,scriptDirty:!!(scriptName&&project&&$('code').value!==scriptBank()[scriptName]),scriptEditor:scriptName?{name:scriptName,text:$('code').value}:null,view:document.body.classList.contains('home-screen')?'home':gameMode?'game-preview':'scene',playing,camera:{position:camera.position.toArray(),target:orbit.target.toArray()},lastBuild,console:$('log').textContent.slice(-50000),previewOnly:true,authDialogOpen:$('sshLoginDialog').open,worldPreview:{...worldView.state},launchScene};},
 capture(){if(document.body.classList.contains('home-screen'))return {state:this.state()};if(!project)throw Error('Project is loading');renderViews();return {state:this.state(),scene:captureNativeOr(renderer),gamePreview:captureNativeOr(previewRenderer)};},
 select(id){if(!activeScene().entities.some(e=>e.id===id))throw Error('Object was not found in the active scene');select(id);return this.state();}
};
for(const [cls,variable,axis,side,min,max] of [['left','--left','x','left',150,440],['right','--right','x','right',210,500],['bottom','--bottom','y','bottom',130,500]]){
 const bar=element('div','splitter splitter-'+cls);bar.setAttribute('role','separator');bar.setAttribute('aria-label','Panel size: '+cls);bar.setAttribute('aria-orientation',axis==='x'?'vertical':'horizontal');document.body.append(bar);
 bar.onpointerdown=ev=>{bar.setPointerCapture(ev.pointerId);document.body.classList.add('resizing');};
 bar.onpointermove=ev=>{if(!bar.hasPointerCapture(ev.pointerId))return;let n=axis==='y'?innerHeight-ev.clientY-22:(side==='right'?innerWidth-ev.clientX:ev.clientX);n=Math.max(min,Math.min(max,n));document.documentElement.style.setProperty(variable,n+'px');};
 bar.onpointerup=ev=>{bar.releasePointerCapture(ev.pointerId);document.body.classList.remove('resizing');};
}

let sshLoginResolve=null;
async function ensureSSH(){
 try{await api('test-ssh',{});return true;}
 catch(e){if(e.code!=='SSH_AUTH_REQUIRED')throw e;return requestSSHLogin(e.message);}
}
function requestSSHLogin(message){
 if(sshLoginResolve)throw Error('SSH sign-in is already in progress');
 const dialog=$('sshLoginDialog');$('sshLoginTarget').textContent=config.settings.user+'@'+config.settings.host;
 $('sshLoginError').textContent=message;$('sshLoginPassword').value='';dialog.showModal();$('sshLoginPassword').focus();
 return new Promise(resolve=>sshLoginResolve=resolve);
}
function finishSSHLogin(ok){const resolve=sshLoginResolve;sshLoginResolve=null;$('sshLoginPassword').value='';$('sshLoginDialog').close();resolve?.(ok);}
$('sshLoginCancel').onclick=()=>finishSSHLogin(false);
$('sshLoginDialog').addEventListener('cancel',ev=>{ev.preventDefault();finishSSHLogin(false);});
$('sshLoginForm').onsubmit=async ev=>{
 ev.preventDefault();$('sshLoginSubmit').disabled=true;$('sshLoginError').textContent='Connecting…';
 try{await api('session-login',{password:$('sshLoginPassword').value});finishSSHLogin(true);}
 catch(e){$('sshLoginError').textContent=e.message;$('sshLoginPassword').value='';$('sshLoginPassword').focus();}
 finally{$('sshLoginSubmit').disabled=false;}
};

function nativeWorkspace(){
 const native=isNative();document.body.classList.toggle('native-project',native);
 for(const id of nativeBlocked)if($(id))$(id).disabled=native||busy;
 $('scenes').disabled=native||busy;$('importFile').disabled=native;
 $('sceneView').textContent=native?'Project':'Scene';$('gameView').hidden=native;
 document.querySelector('.script-editor .muted').textContent=native?'Native C++ · voxel engine / RSX':'Native C++ · Forge.h API';
 $('saveScript').textContent=native?'Save source':'Save script';
 if(native){
   $('viewModeLabel').textContent='Last RPCS3 screenshot · not live';
   if(!nativeImage.parentElement)viewport.append(nativeImage);
   const url='/api/native-preview?id='+project.id;if(nativeImage.getAttribute('src')!==url)nativeImage.src=url;
 }else{nativeImage.remove();$('viewModeLabel').textContent=gameMode?'Game camera · visual preview':'Perspective';}
}
function renderNativeTree(){
 const tree=$('tree');tree.replaceChildren();$('objectCount').textContent='C++';
 for(const name of Object.keys(scriptBank())){const row=element('button','native-file',name);row.onclick=()=>{openScript(name);showTab('scripts');};tree.append(row);}
}
function captureNativeOr(target){
 if(!isNative())return target.domElement.toDataURL('image/png');
 if(!nativeImage.complete||!nativeImage.naturalWidth)throw Error('RPCS3 screenshot has not finished loading');
 const canvas=document.createElement('canvas');canvas.width=nativeImage.naturalWidth;canvas.height=nativeImage.naturalHeight;canvas.getContext('2d').drawImage(nativeImage,0,0);return canvas.toDataURL('image/png');
}

function updateBuildFields(){const mode=$('settingsForm').elements.buildMode.value;document.querySelectorAll('[data-build]').forEach(el=>el.hidden=el.dataset.build!==mode);}
$('settingsForm').elements.buildMode.onchange=updateBuildFields;
async function ensureBuildTools(){if(config.settings.buildMode==='local'){await api('test-local',{});return true;}return ensureSSH();}

function storeDraft(){
 if(!project||isNative()||!dirty)return;try{const draft=structuredClone(project);if(scriptName)draft.scripts[scriptName]=$('code').value;localStorage.setItem('forge.draft.'+project.id,JSON.stringify({time:Date.now(),project:draft}));}catch(error){status('Draft recovery could not be stored: '+error.message);}
}
setInterval(async()=>{
 if(!project||busy||isNative()||assetPollBusy||document.body.classList.contains('home-screen'))return;assetPollBusy=true;const pid=project.id;
 try{const signatures=await api('assets/status?id='+pid);if(project?.id!==pid)return;
 if(assetSignatures&&JSON.stringify(signatures)!==JSON.stringify(assetSignatures)){
  const result=await api('assets/refresh?id='+pid);if(project?.id!==pid)return;
  for(const [id,a]of Object.entries(result.assets)){project.assets[id]=a;cache.delete(pid+'/'+id);}if(result.textures)project.textures={...project.textures,...result.textures};
  await renderScene();toast('Assets reloaded from disk. Scene edits preserved.');
 }assetSignatures=signatures;
 }catch(error){const message='Asset reload: '+error.message;if(window.lastAssetError!==message){toast(message,true);window.lastAssetError=message;}}
 finally{assetPollBusy=false;}
},3000);

window.addEventListener('beforeunload',storeDraft);
