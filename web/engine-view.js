import * as THREE from 'three';
import {createMesh} from './iyam.js';
import {previewAttachments,previewPath,applyMaterials} from './engine-ui.js';
const helpers=new Map(),pending=new Map();let profiler,enabled=false,lastProfile=0;
export function installProfiler(viewport,toolbar){
 const button=document.createElement('button');button.textContent='Profiler';button.title='Editor counters; add a Profiler component for the native HUD';toolbar.append(button);profiler=document.createElement('pre');profiler.className='engine-profiler';profiler.hidden=true;viewport.append(profiler);button.onclick=()=>{enabled=!enabled;profiler.hidden=!enabled;};
}
export function updateEngineView(p,objects,scene,camera,modelData,viewClones){
 const alive=new Set();
 for(const e of p.scenes[p.activeScene].entities){
  const o=objects.get(e.id);if(!o)continue;const lod=e.engine?.LOD;
  if(lod){const distance=o.position.distanceTo(camera.position);o.visible=e.visible!==false&&distance<=lod.maxDistance;let asset=e.asset;for(const level of lod.levels)if(distance>=level.distance)asset=level.asset;
   if(asset&&asset!==(o.userData.lodAsset??e.asset)&&!pending.has(e.id)){const task=modelData(asset).then(data=>{if(objects.get(e.id)!==o)return;const atlasUrl=p.materialAtlas?'/texture/'+p.id+'/atlas.png?v='+p.materialAtlas.sha256:'/forge-atlas.png';const replacement=createMesh(data,!!p.assets[asset].usesForgeAtlas,atlasUrl),geometry=replacement.geometry;for(const material of (Array.isArray(o.material)?o.material:[o.material]))material.dispose();o.material=replacement.material;o.geometry.dispose();o.geometry=geometry;o.userData.model=data;o.userData.lodAsset=asset;o.userData.bones=null;applyMaterials(o,e,p);const clone=viewClones.get(e.id);if(clone){clone.geometry=geometry;clone.material=o.material;}}).catch(error=>{o.userData.lodError=error.message;}).finally(()=>pending.delete(e.id));pending.set(e.id,task);}
  }
 }
 previewAttachments(p,objects);
 for(const e of p.scenes[p.activeScene].entities){
  const o=objects.get(e.id);if(!o)continue;
  for(const type of ['bones','route']){
   const wanted=type==='bones'?o.userData.showBones:o.userData.showRoute,key=e.id+':'+type;
   if(!wanted)continue;alive.add(key);let helper=helpers.get(key);if(!helper){helper=new THREE.LineSegments(new THREE.BufferGeometry(),new THREE.LineBasicMaterial({color:type==='bones'?0x79d4ed:0xf1cf69,depthTest:false}));helper.renderOrder=100;helper.userData.type=type;helpers.set(key,helper);scene.add(helper);}const points=[];
   if(type==='bones'){const data=o.userData.model;o.updateMatrixWorld(true);for(const b of data?.bones??[])if(b.parent>=0){const a=o.userData.bones?.get(data.bones[b.parent].name),end=o.userData.bones?.get(b.name);if(a&&end){for(const m of [a,end])points.push(new THREE.Vector3().setFromMatrixPosition(m).applyMatrix4(o.matrixWorld));}}}
   else{const hash=JSON.stringify([e.position,e.engine?.NavigationAgent,e.engine?.NPC?.patrol,p.scenes[p.activeScene].entities.filter(e=>e.collider).map(e=>[e.position,e.scale])]);if(helper.userData.hash!==hash){helper.userData.path=previewPath(e,p);helper.userData.hash=hash;}const path=helper.userData.path??[];for(let i=1;i<path.length;i++)points.push(new THREE.Vector3(...path[i-1]),new THREE.Vector3(...path[i]));}
   helper.geometry.dispose();helper.geometry=new THREE.BufferGeometry().setFromPoints(points);helper.visible=o.visible;
  }
 }
 for(const [key,helper]of helpers)if(!alive.has(key)){scene.remove(helper);helper.geometry.dispose();helper.material.dispose();helpers.delete(key);}
}
export function updateProfiler(p,renderer,frameMs){
 if(!enabled||performance.now()-lastProfile<400)return;lastProfile=performance.now();const assets=Object.values(p.assets),textures=Object.values(p.textures??{});profiler.textContent=`EDITOR PREVIEW\nFrame interval ${frameMs.toFixed(2)} ms\n${renderer.info.render.calls} draw calls · ${renderer.info.render.triangles} triangles\n${p.scenes[p.activeScene].entities.length} objects · ${assets.reduce((n,a)=>n+(a.bones?.length??0),0)} bones\nAsset files ${(assets.reduce((n,a)=>n+a.bytes,0)/1048576).toFixed(2)} MiB\nTexture upload estimate ${(textures.reduce((n,t)=>n+t.size*t.size*4,0)/1048576).toFixed(2)} MiB\nPreview counters are not PS3 GPU timings.`;
}
