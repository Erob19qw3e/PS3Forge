import * as THREE from 'three';
import {parseSkeleton,sampleSkeleton} from './skeleton.js';
const atlasTextures=new Map();
function sharedAtlas(url='/forge-atlas.png'){if(!atlasTextures.has(url)){const texture=new THREE.TextureLoader().load(url);texture.colorSpace=THREE.SRGBColorSpace;texture.flipY=false;atlasTextures.set(url,texture);}return atlasTextures.get(url);}
export function parseIYAM(buffer){
 if(buffer.byteLength>=8&&new DataView(buffer).getUint32(4)===2)return parseSkeleton(buffer);
 const d=new DataView(buffer);let p=0;
 const u32=()=>{const x=d.getUint32(p);p+=4;return x;};const f32=()=>{const x=d.getFloat32(p);p+=4;return x;};
 if(u32()!==0x4959414d||u32()!==1)throw Error('Invalid model format');
 const nv=u32(),ni=u32(),ng=u32(),nc=u32(),nf=u32(),stride=u32();
 if(!nv||nv>20000||!ni||ni>1000000||ni%3||!ng||ng>64||!nc||nc>128||!nf||nf>4096||nv*nf*32>64*1024*1024||stride!==32||32+ng*24+nc*48+ni*2+nv*nf*32!==buffer.byteLength)throw Error('Invalid model dimensions');
 const groups=[];for(let i=0;i<ng;i++)groups.push({start:u32(),count:u32(),color:[f32(),f32(),f32()],tint:u32()});
 const clips=[];for(let i=0;i<nc;i++){const bytes=new Uint8Array(buffer,p,32);const end=bytes.indexOf(0);const name=new TextDecoder().decode(bytes.slice(0,end<0?32:end));p+=32;clips.push({name,first:u32(),count:u32(),fps:f32(),loop:!!u32()});}
 const indices=new Uint16Array(ni);for(let i=0;i<ni;i++){indices[i]=d.getUint16(p);p+=2;}
 const poses=new Float32Array(nv*nf*8);for(let i=0;i<poses.length;i++)poses[i]=f32();
 return {nv,indices,groups,clips,poses};
}
export function createMesh(data,useAtlas=false,atlasUrl='/forge-atlas.png'){
 const geometry=new THREE.BufferGeometry();geometry.setIndex(new THREE.BufferAttribute(data.indices,1));
 geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(data.nv*3),3).setUsage(THREE.DynamicDrawUsage));
 geometry.setAttribute('normal',new THREE.BufferAttribute(new Float32Array(data.nv*3),3).setUsage(THREE.DynamicDrawUsage));
 const uv=new Float32Array(data.nv*2);for(let i=0;i<data.nv;i++){uv[i*2]=data.poses[i*8+6];uv[i*2+1]=data.poses[i*8+7];}geometry.setAttribute('uv',new THREE.BufferAttribute(uv,2));
 const materials=data.groups.map(g=>new THREE.MeshStandardMaterial({color:new THREE.Color(...g.color),map:useAtlas&&g.tint?sharedAtlas(atlasUrl):null,alphaTest:.45,roughness:.8,metalness:.08,side:THREE.DoubleSide}));
 data.groups.forEach((g,i)=>geometry.addGroup(g.start,g.count,i));
 const mesh=new THREE.Mesh(geometry,materials);mesh.frustumCulled=false;mesh.userData.model=data;mesh.userData.time=0;return mesh;
}
export function sampleMesh(mesh,name,time,tint){
 const data=mesh.userData.model;const c=data.clips.find(c=>c.name===name)||data.clips[0];let frame=Math.max(0,time*c.fps);frame=c.loop?frame%c.count:Math.min(frame,c.count-1);
 const a=Math.floor(frame),b=c.loop?(a+1)%c.count:Math.min(a+1,c.count-1),t=frame-a;
 const positions=mesh.geometry.attributes.position.array,normals=mesh.geometry.attributes.normal.array;
 if(data.bones){
  const state=mesh.userData;if(state.lastClip&&state.lastClip!==name)state.transition={clip:data.clips.find(x=>x.name===state.lastClip),time:state.lastTime,start:performance.now()};
  const transition=state.transition,alpha=transition?Math.min(1,(performance.now()-transition.start)/Math.max(1,(state.blendDuration??.12)*1000)):1;
  state.bones=sampleSkeleton(data,c,time,positions,normals,transition?.clip,transition?(transition.time+(performance.now()-transition.start)/1000):0,alpha);state.lastClip=name;state.lastTime=time;
 }else for(let i=0;i<data.nv;i++)for(let k=0;k<3;k++){const x=((c.first+a)*data.nv+i)*8+k,y=((c.first+b)*data.nv+i)*8+k;positions[i*3+k]=data.poses[x]+(data.poses[y]-data.poses[x])*t;normals[i*3+k]=data.poses[x+3]+(data.poses[y+3]-data.poses[x+3])*t;}
 mesh.geometry.attributes.position.needsUpdate=true;mesh.geometry.attributes.normal.needsUpdate=true;
 mesh.material.forEach((m,i)=>{const c=m.userData.forgeColor??[1,1,1];m.color.setRGB(data.groups[i].color[0]*tint[0]*c[0],data.groups[i].color[1]*tint[1]*c[1],data.groups[i].color[2]*tint[2]*c[2]);});
 return c;
}
