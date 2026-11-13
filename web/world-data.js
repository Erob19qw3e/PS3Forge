// Pure FWS reader used by the editor. The server validates the source resource.
export function parseWorld(buffer,hiddenRanges=[]){
 const d=new DataView(buffer),u=p=>d.getUint32(p),f=p=>d.getFloat32(p),version=u(4);
 if(buffer.byteLength<64||u(0)!==0x46575331||![1,2,3,4].includes(version)||u(44)!==buffer.byteLength)throw Error('Invalid world resource');
 const nm=u(8),ni=u(12),mo=u(24),io=u(28);if(nm>4096||ni>100000||io!==64+nm*24||mo!==64)throw Error('Invalid world tables');
 const models=Array.from({length:nm},(_,i)=>{const p=mo+i*24;return {offset:u(p),bytes:u(p+4),nv:u(p+8),ni:u(p+12),ng:u(p+16),finer:u(p+20)-1};});
 const instances=Array.from({length:ni},(_,id)=>{const p=io+id*88;return {id,model:u(p),flags:u(p+4),layers:u(p+12),matrix:Array.from({length:12},(_,j)=>f(p+16+j*4)),lo:Array.from({length:3},(_,j)=>f(p+64+j*4)),hi:Array.from({length:3},(_,j)=>f(p+76+j*4)),hidden:hiddenRanges.some(([a,b])=>id>=a&&id<b)};});
 const textures=[],sets=[];if(version>=3){let p=u(60);if(u(p)!==0x46575431)throw Error('Invalid world textures');const count=u(p+8);p+=16;for(let i=0;i<count;i++){const width=u(p),size=u(p+4);p+=8;if(size!==width*width*4||p+size>buffer.byteLength)throw Error('Invalid world image');textures.push({width,offset:p,size});p+=size;}if(version===4){const count=u(p);p+=4;for(let i=0;i<count;i++){sets.push([u(p),u(p+4),u(p+8)]);p+=12;}}}
 const child=new Set(models.filter(m=>m.finer>=0).map(m=>m.finer));const bases=models.map((_,i)=>i).filter(i=>!child.has(i));
 return {buffer,d,version,models,instances,textures,sets,bases,near:version>=2?f(52):20,mid:version>=2?f(56):60};
}
export function textureFor(world,tag,instance){const base=tag&0xffffff,slot=tag>>>24;if(world.version<4||!instance.layers||slot>3)return base;const set=world.sets[instance.layers-1];let selected=set[0]||base;if(slot&&set[slot-1])selected=set[slot-1];return selected;}
export function readModel(world,id){
 const m=world.models[id],d=world.d;let p=m.offset;const groups=[];for(let i=0;i<m.ng;i++,p+=24)groups.push({start:d.getUint32(p),count:d.getUint32(p+4),color:[d.getFloat32(p+8),d.getFloat32(p+12),d.getFloat32(p+16)],tag:d.getUint32(p+20)});
 const indices=new Uint16Array(m.ni);for(let i=0;i<m.ni;i++,p+=2)indices[i]=d.getUint16(p);
 const positions=new Float32Array(m.nv*3),normals=new Float32Array(m.nv*3),uv=new Float32Array(m.nv*2);for(let i=0;i<m.nv;i++,p+=32){for(let j=0;j<3;j++){positions[i*3+j]=d.getFloat32(p+j*4);normals[i*3+j]=d.getFloat32(p+12+j*4);}uv[i*2]=d.getFloat32(p+24);uv[i*2+1]=d.getFloat32(p+28);}
 return {groups,indices,positions,normals,uv};
}
export function selectWorld(world,x,z,settings){
 const candidates=[];for(const i of world.instances){if(!(i.flags&1)||i.hidden)continue;const dx=Math.max(i.lo[0]-x,0,x-i.hi[0]),dz=Math.max(i.lo[2]-z,0,z-i.hi[2]),distance=dx*dx+dz*dz;if(distance<=settings.radius**2)candidates.push([distance,i]);}candidates.sort((a,b)=>a[0]-b[0]||a[1].id-b[1].id);
 const selected=[],models=new Set();let vertices=0,draws=0;for(const [distance,instance]of candidates){const chain=[];for(let id=instance.model;id>=0;id=world.models[id].finer){if(chain.length>=8)throw Error('Invalid LOD chain');chain.push(id);}let rank=distance<world.near**2?chain.length-1:distance<world.mid**2?Math.max(0,chain.length-2):0;for(;rank>=0;rank--){const id=chain[rank],m=world.models[id];if(vertices+m.nv>settings.vertexBudget||draws+m.ng>settings.maxDraws||(!models.has(id)&&models.size>=settings.maxModels))continue;models.add(id);vertices+=m.nv;draws+=m.ng;selected.push({instance,model:id});break;}}
 return {selected,models,vertices,draws,candidates:candidates.length};
}
