import * as THREE from 'three';
export function parseSkeleton(buffer){
 const d=new DataView(buffer);let p=0;const u=()=>{const v=d.getUint32(p);p+=4;return v;},f=()=>{const v=d.getFloat32(p);p+=4;if(!Number.isFinite(v))throw Error('Non-finite skeletal value');return v;},name=()=>{const a=new Uint8Array(buffer,p,32);p+=32;const end=a.indexOf(0);if(end<1)throw Error('Invalid skeletal name');return new TextDecoder().decode(a.slice(0,end));};
 if(u()!==0x4959414d||u()!==2)throw Error('Invalid skeletal format');
 const nv=u(),ni=u(),ng=u(),nc=u(),nf=u(),stride=u(),nb=u(),ne=u(),flags=u(),reserved=u();
 if(!nv||nv>20000||!ni||ni>1000000||ni%3||!ng||ng>64||!nc||nc>128||!nf||nf>4096||!nb||nb>128||ne>1024||stride!==56||flags||reserved||48+ng*24+nc*48+nb*100+ne*40+ni*2+nv*56+nf*nb*40!==buffer.byteLength||buffer.byteLength>64*1048576)throw Error('Invalid skeletal dimensions');
 const groups=[];for(let i=0;i<ng;i++){const g={start:u(),count:u(),color:[f(),f(),f()],tint:u()};if(g.start+g.count>ni||g.count%3||g.tint>1||g.color.some(x=>x<0||x>1))throw Error('Invalid skeletal group');groups.push(g);}
 const clips=[];for(let i=0;i<nc;i++){const c={name:name(),first:u(),count:u(),fps:f(),loop:u()};if(!c.count||c.first+c.count>nf||c.fps<=0||c.fps>120||c.loop>1)throw Error('Invalid skeletal clip');clips.push(c);}
 const bones=[];for(let i=0;i<nb;i++){const n=name(),parent=d.getInt32(p);p+=4;const values=Array.from({length:16},f);if(parent< -1||parent>=i)throw Error('Invalid bone hierarchy');bones.push({name:n,parent,inverseBind:new THREE.Matrix4().set(...values)});}
 if(new Set(bones.map(b=>b.name)).size!==nb||new Set(clips.map(c=>c.name)).size!==nc)throw Error('Duplicate skeletal names');
 const events=[];for(let i=0;i<ne;i++){const e={clip:u(),time:f(),name:name()};if(e.clip>=nc||e.time<0||e.time>clips[e.clip].count/clips[e.clip].fps)throw Error('Invalid animation event');events.push(e);}
 const indices=new Uint16Array(ni);for(let i=0;i<ni;i++){indices[i]=d.getUint16(p);p+=2;if(indices[i]>=nv)throw Error('Invalid skeletal index');}
 const poses=new Float32Array(nv*8),joints=new Uint16Array(nv*4),weights=new Float32Array(nv*4);
 for(let i=0;i<nv;i++){for(let j=0;j<8;j++)poses[i*8+j]=f();for(let j=0;j<4;j++){joints[i*4+j]=d.getUint16(p);p+=2;if(joints[i*4+j]>=nb)throw Error('Invalid joint');}let sum=0;for(let j=0;j<4;j++){const w=f();if(w<0||w>1)throw Error('Invalid weight');weights[i*4+j]=w;sum+=w;}if(Math.abs(sum-1)>.001)throw Error('Invalid weight sum');}
 const keys=new Float32Array(nf*nb*10);for(let i=0;i<keys.length;i++)keys[i]=f();for(let i=0;i<keys.length;i+=10){let q=0;for(let j=3;j<7;j++)q+=keys[i+j]**2;if(Math.abs(q-1)>.003||[7,8,9].some(j=>keys[i+j]<.0001||keys[i+j]>100))throw Error('Invalid skeletal key');}
 return {nv,nf,indices,groups,clips,poses,bones,joints,weights,keys,events};
}
function localKey(data,c,time,bone){
 let frame=Math.max(0,time*c.fps);frame=c.loop?frame%c.count:Math.min(frame,c.count-1);const a=Math.floor(frame),b=c.loop?(a+1)%c.count:Math.min(a+1,c.count-1),t=frame-a,x=((c.first+a)*data.bones.length+bone)*10,y=((c.first+b)*data.bones.length+bone)*10;
 const v=Array.from({length:10},(_,j)=>data.keys[x+j]+(data.keys[y+j]-data.keys[x+j])*t);let dot=0;for(let j=3;j<7;j++)dot+=data.keys[x+j]*data.keys[y+j];for(let j=3;j<7;j++)v[j]=data.keys[x+j]+((dot<0?-data.keys[y+j]:data.keys[y+j])-data.keys[x+j])*t;const length=Math.hypot(...v.slice(3,7));for(let j=3;j<7;j++)v[j]/=length;return v;
}
export function sampleSkeleton(data,clip,time,positions,normals,previous=null,previousTime=0,alpha=1){
 const world=[],skin=[],normal=[];
 for(let i=0;i<data.bones.length;i++){
  const v=localKey(data,clip,time,i);
  if(previous&&alpha<1){const a=localKey(data,previous,previousTime,i),dot=a.slice(3,7).reduce((n,x,j)=>n+x*v[j+3],0),q=a.slice(3,7).map((x,j)=>x+((dot<0?-v[j+3]:v[j+3])-x)*alpha),length=Math.hypot(...q);for(let j=0;j<3;j++){v[j]=a[j]+(v[j]-a[j])*alpha;v[j+7]=a[j+7]+(v[j+7]-a[j+7])*alpha;}v.splice(3,4,...q.map(x=>x/length));}
  const m=new THREE.Matrix4().compose(new THREE.Vector3(...v.slice(0,3)),new THREE.Quaternion(...v.slice(3,7)),new THREE.Vector3(...v.slice(7,10)));if(data.bones[i].parent>=0)m.premultiply(world[data.bones[i].parent]);world.push(m);skin.push(m.clone().multiply(data.bones[i].inverseBind));normal.push(new THREE.Matrix3().getNormalMatrix(skin[i]));
 }
 const p=new THREE.Vector3(),n=new THREE.Vector3(),out=new THREE.Vector3(),nor=new THREE.Vector3();
 for(let i=0;i<data.nv;i++){out.set(0,0,0);nor.set(0,0,0);for(let j=0;j<4;j++){const w=data.weights[i*4+j],b=data.joints[i*4+j];if(!w)continue;p.fromArray(data.poses,i*8).applyMatrix4(skin[b]);n.fromArray(data.poses,i*8+3).applyMatrix3(normal[b]);out.addScaledVector(p,w);nor.addScaledVector(n,w);}out.toArray(positions,i*3);nor.normalize().toArray(normals,i*3);}
 return new Map(data.bones.map((b,i)=>[b.name,world[i]]));
}
