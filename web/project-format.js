// Disk/API components are authoritative. The editor uses a flat working copy.
export function entityScripts(e) {return e.scripts??(e.script?[{name:e.script,enabled:true}]:[]);}
export function setEntityScripts(e,items) {e.script='';e.scripts=structuredClone(items);}
export function decodeProject(value) {
 const p=structuredClone(value),v=p.formatVersion??1;
 if(!Number.isInteger(v)||![1,2,3,4].includes(v))throw Error('Unsupported project format version');
 if(p.nativeProject){if(v!==1)throw Error('Unsupported native project format');return p;}
 if(v===1)return p;
 for(const s of p.scenes)for(const e of s.entities){
  const c=e.components;if(!c?.Transform||!c?.MeshRenderer)throw Error('Required components are missing');
  Object.assign(e,c.Transform,c.MeshRenderer,{clip:c.Animator?.clip??'Idle',script:c.Script?.name??'',collider:!!c.BoxCollider,gravity:!!c.RigidBody});
  if(v>=3){const items=c.Scripts?.items??[];if(items.length===1&&items[0].enabled)e.script=items[0].name;else if(items.length)setEntityScripts(e,items);}
  if(c.Engine)e.engine=c.Engine.items;
  delete e.components;
 }
 delete p.formatVersion;return p;
}
export function encodeProject(value) {
 const p=structuredClone(value);if(p.nativeProject)return p;
 const extended=Object.keys(p.materials??{}).length||Object.keys(p.textures??{}).length||Object.values(p.assets??{}).some(a=>a.format===2)||p.scenes.some(s=>s.entities.some(e=>Object.keys(e.engine??{}).length));
 for(const s of p.scenes)for(const e of s.entities){
  const c={Transform:{position:e.position,rotation:e.rotation,scale:e.scale},MeshRenderer:{kind:e.kind,color:e.color,asset:e.asset}};
  if(e.kind==='model')c.Animator={clip:e.clip};
  const items=entityScripts(e);if(items.length)c.Scripts={items};if(e.collider)c.BoxCollider={};if(e.gravity)c.RigidBody={useGravity:true};
  if(Object.keys(e.engine??{}).length)c.Engine={items:e.engine};
  for(const k of ['position','rotation','scale','kind','color','asset','clip','script','scripts','collider','gravity','engine'])delete e[k];
  e.components=c;
 }
 p.formatVersion=extended?4:3;return p;
}
