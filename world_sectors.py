"""Validated static-world resource. Model geometry is shared; instances stream by sectors.
FWS1 is BE: 64-byte header, 24-byte mesh records, 88-byte instances, 16-byte cells,
4-byte references, then groups(24)/indices(2)/vertices(32) per static model.
"""
from pathlib import Path
import math,struct,hashlib,re
MAX_BYTES=80*1024*1024
FIELDS={'file','sha256','bytes','models','instances','cells','target','radius','vertexBudget','maxModels','maxDraws','cacheBytes'}
def validate(p):
 m=p.get('worldSectors')
 if m is None:return
 if not isinstance(m,dict)or (not FIELDS<=set(m)or set(m)-FIELDS-{'format','renderPolicy','collisionRadius'}) or m['file']!='world.fws' or not re.fullmatch('[a-f0-9]{64}',str(m['sha256'])):raise ValueError('Invalid world sector metadata')
 if type(m.get('format',1))is not int or m.get('format',1)not in(1,2,3,4):raise ValueError('Unsupported world format')
 if 'renderPolicy' in m and (not isinstance(m['renderPolicy'],str) or m['renderPolicy'] not in p.get('scripts',{})):raise ValueError('Invalid world render policy')
 collision_radius=m.get('collisionRadius',12)
 if type(collision_radius) not in (int,float) or not 1<=collision_radius<=12:raise ValueError('Invalid collision radius')
 extended=m.get('format',1)>=4
 for key,lo,hi in [('bytes',64,MAX_BYTES),('models',1,4096),('instances',1,100000),('cells',1,20000),('vertexBudget',1,192000 if extended else 64000),('maxModels',1,160 if extended else 32),('maxDraws',1,1280 if extended else 512),('cacheBytes',65536,32*1024*1024)]:
  if type(m[key])is not int or not lo<=m[key]<=hi:raise ValueError('Invalid world sector '+key)
 if type(m['radius'])not in(int,float)or not math.isfinite(m['radius'])or not 16<=m['radius']<=500:raise ValueError('World radius must be 16-500 metres')
 entities=[e for s in p['scenes']for e in s['entities']];target=next((e for e in entities if e['id']==m['target']),None)
 if not target:raise ValueError('World sector target is missing')
 scene=next(s for s in p['scenes']if target in s['entities'])
 static=sum(max([p['assets'][e['asset']]['vertices']]+[p['assets'][x['asset']]['vertices']for x in e.get('engine',{}).get('LOD',{}).get('levels',[])])for e in entities if e['kind']=='model')
 if static+m['vertexBudget']>(256000 if extended else 64000):raise ValueError('Scene plus streamed world exceeds resident instance vertex limit')
 if len(p['assets'])+m['maxModels']>(192 if extended else 32):raise ValueError('Scene plus world cache exceeds resident model definition limit')
 if sum(a['bytes']for a in p['assets'].values())+m['bytes']>MAX_BYTES:raise ValueError('Scene and streamed resource exceed 80 MiB')
def inspect(raw):
 if len(raw)<64 or len(raw)>MAX_BYTES:raise ValueError('World resource size')
 version=struct.unpack_from('>I',raw,4)[0]
 h=struct.unpack_from('>12I3fI',raw)if version>=2 else struct.unpack_from('>12If3I',raw)
 magic,ver,nm,ni,nc,nr,mo,io,co,ro,do,total,cell,*reserved=h
 near,mid=(reserved[0],reserved[1])if ver>=2 else(20.,60.)
 lod_mid=mid
 if ver>=2 and ((ver==2 and reserved[2])or not all(math.isfinite(x)for x in [near,mid])or not 1<=near<mid<=500):raise ValueError('Invalid LOD distances')
 if magic!=0x46575331 or ver not in(1,2,3,4) or not(1<=nm<=4096 and 1<=ni<=100000 and 1<=nc<=20000 and nr<=2000000)or (ver==1 and reserved!=[0,0,0])or not math.isfinite(cell)or not 16<=cell<=256:raise ValueError('World resource header')
 if (mo,io,co,ro,do,total)!=(64,64+nm*24,64+nm*24+ni*88,64+nm*24+ni*88+nc*16,64+nm*24+ni*88+nc*16+nr*4,len(raw)):raise ValueError('World resource table bounds')
 texture_start=reserved[2]if ver>=3 else len(raw)
 texture_count=0;layer_count=0;collision_triangles=0
 if ver>=3:
  if not do<texture_start<len(raw)-16:raise ValueError("World texture offset")
  magic,tver,texture_count,tsize=struct.unpack_from(">4I",raw,texture_start)
  if magic!=0x46575431 or tver!=(2 if ver==4 else 1) or not 1<=texture_count<=(1024 if ver==4 else 64) or tsize!=len(raw)-texture_start:raise ValueError("World texture header")
  at=texture_start+16;gpu=0
  for i in range(texture_count):
   if at+8>len(raw):raise ValueError("World texture record")
   width,size=struct.unpack_from(">2I",raw,at);at+=8
   if width not in(64,128,256)or size!=width*width*4 or at+size>len(raw):raise ValueError("World texture size")
   at+=size;gpu+=size
  if ver==4:
   if at+4>len(raw):raise ValueError('World texture sets')
   layer_count=struct.unpack_from('>I',raw,at)[0];at+=4
   if layer_count>1024 or at+layer_count*12+4>len(raw):raise ValueError('World texture set bounds')
   if any(t[0]>texture_count for t in struct.iter_unpack('>I',raw[at:at+layer_count*12])):raise ValueError('World texture set index')
   at+=layer_count*12;collision_models=struct.unpack_from('>I',raw,at)[0];at+=4;seen_collision=set()
   if collision_models>nm:raise ValueError('World collision models')
   for i in range(collision_models):
    if at+8>len(raw):raise ValueError('World collision record')
    model,count=struct.unpack_from('>2I',raw,at);at+=8
    if model>=nm or model in seen_collision or count>200000 or at+count*36>len(raw):raise ValueError('World collision model bounds')
    seen_collision.add(model);collision_triangles+=count
    if collision_triangles>500000 or any(not math.isfinite(v[0])or abs(v[0])>100 for v in struct.iter_unpack('>f',raw[at:at+count*36])):raise ValueError('World collision data')
    at+=count*36
  if at!=len(raw)or gpu>16*1024*1024:raise ValueError("World texture budget")
 models=[];links=[];cursor=do
 for i in range(nm):
  off,size,nv,nix,ng,finer=struct.unpack_from('>6I',raw,mo+i*24)
  if off!=cursor or (finer!=0 if ver==1 else finer>nm)or not(0<nv<=20000 and 0<nix<=1000000 and nix%3==0 and 0<ng<=64)or size!=ng*24+nix*2+nv*32 or off+size>texture_start:raise ValueError('World model bounds')
  for j in range(ng):
   start,count,r,g,b,t=struct.unpack_from('>II3fI',raw,off+j*24)
   if start+count>nix or count%3 or (t&0xffffff)>texture_count or (t>>24)>(6 if ver==4 else 0) or not all(math.isfinite(x)and 0<=x<=1 for x in [r,g,b]):raise ValueError('World material group')
  index=off+ng*24
  if any(v[0]>=nv for v in struct.iter_unpack('>H',raw[index:index+nix*2])):raise ValueError('World index')
  for v in struct.iter_unpack('>8f',raw[index+nix*2:off+size]):
   if not all(math.isfinite(x)for x in v)or any(abs(x)>100 for x in v[:3])or any(abs(x)>2 for x in v[3:6]):raise ValueError('World vertex')
  models.append((nv,nix,ng));links.append(finer-1);cursor+=size
 for i in range(nm):
  seen=set();k=i
  while k>=0:
   if k in seen or len(seen)>=8:raise ValueError('Invalid LOD chain')
   seen.add(k);k=links[k]
 if cursor!=texture_start:raise ValueError('Trailing world data')
 flags=[]
 for i in range(ni):
  mid,flag,source,zero,*v=struct.unpack_from('>4I18f',raw,io+i*88)
  if mid>=nm or flag&~3 or (zero>layer_count if ver==4 else zero!=0) or source!=i or not all(math.isfinite(x)and abs(x)<1e7 for x in v)or any(v[12+j]>v[15+j]for j in range(3)):raise ValueError('World instance')
  flags.append(flag)
 seen=set();coverage=set()
 for i in range(nc):
  x,z,first,count=struct.unpack_from('>iiII',raw,co+i*16)
  if (x,z)in seen or first+count>nr:raise ValueError('World cell')
  seen.add((x,z))
  for j in range(first,first+count):
   k=struct.unpack_from('>I',raw,ro+j*4)[0]
   if k>=ni or not flags[k]&1:raise ValueError('World sector reference')
   lo=struct.unpack_from('>6f',raw,io+k*88+64);cx=(x+.5)*cell;cz=(z+.5)*cell;dx=max(lo[0]-cx,0,cx-lo[3]);dz=max(lo[2]-cz,0,cz-lo[5])
   if dx*dx+dz*dz>cell*cell*.5+.1:raise ValueError('World cell location')
   coverage.add(k)
 if coverage!={i for i,f in enumerate(flags)if f&1}:raise ValueError('Incomplete world sector coverage')
 return dict(format=ver,lodNear=near,lodMid=lod_mid,models=nm,instances=ni,cells=nc,bytes=len(raw),renderable=sum(bool(f&1)for f in flags),references=nr,textures=texture_count,textureSets=layer_count,collisionTriangles=collision_triangles)
def read(root,meta):
 raw=(Path(root)/'world'/meta['file']).read_bytes()
 if len(raw)!=meta['bytes']or hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('World resource checksum mismatch')
 info=inspect(raw)
 if info['format']!=meta.get('format',1):raise ValueError('World format metadata mismatch')
 if any(info[k]!=meta[k]for k in ['models','instances','cells']):raise ValueError('World metadata mismatch')
 return raw
