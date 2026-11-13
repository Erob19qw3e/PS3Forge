"""IYAM2: bind vertices, four weights, bone-local TRS keys and named events.

Big endian. Header 12*u32; groups 24 B; clips 48 B; bones 100 B
(name32,parent i32,inverse-bind row-major mat4); events 40 B; u16 indices;
vertices 56 B (8 floats,4 u16 joints,4 floats weights); keys 10 floats/bone/frame.
"""
import math,struct
MAGIC=0x4959414d
def inspect(raw):
 if len(raw)<48:raise ValueError('Truncated skeletal header')
 magic,version,nv,ni,ng,nc,nf,stride,nb,ne,flags,reserved=struct.unpack_from('>12I',raw)
 if magic!=MAGIC or version!=2 or stride!=56 or flags or reserved:raise ValueError('Unsupported skeletal format')
 if not(0<nv<=20000 and 0<ni<=1000000 and ni%3==0 and 0<ng<=64 and 0<nc<=128 and 0<nf<=4096 and 0<nb<=128 and ne<=1024):raise ValueError('Skeletal counts out of range')
 size=48+24*ng+48*nc+100*nb+40*ne+2*ni+56*nv+40*nb*nf
 if size!=len(raw) or size>64*1024*1024:raise ValueError('Skeletal size/budget mismatch')
 def name(b):
  if b'\0' not in b:raise ValueError('Unterminated skeletal name')
  s=b.split(b'\0')[0].decode('utf8')
  if not s or len(s)>31:raise ValueError('Invalid skeletal name')
  return s
 offset=48;groups=[]
 for _ in range(ng):
  start,count,r,g,b,tint=struct.unpack_from('>II3fI',raw,offset);offset+=24
  if start+count>ni or count%3 or tint>1 or any(not math.isfinite(x) or not 0<=x<=1 for x in (r,g,b)):raise ValueError('Invalid skeletal material group')
  groups.append((start,count,r,g,b,tint))
 clips=[]
 for _ in range(nc):
  n,first,count,fps,loop=struct.unpack_from('>32sIIfI',raw,offset);offset+=48
  if not count or first+count>nf or not math.isfinite(fps) or not 0<fps<=120 or loop>1:raise ValueError('Invalid skeletal clip')
  clips.append(dict(name=name(n),first=first,count=count,fps=fps,loop=bool(loop)))
 if len({c['name'] for c in clips})!=nc:raise ValueError('Duplicate skeletal clips')
 bones=[]
 for i in range(nb):
  values=struct.unpack_from('>32si16f',raw,offset);offset+=100
  if not -1<=values[1]<i or any(not math.isfinite(x) or abs(x)>100000 for x in values[2:]):raise ValueError('Invalid bone parent/inverse bind')
  bones.append(dict(name=name(values[0]),parent=values[1],inverseBind=list(values[2:])))
 if len({b['name'] for b in bones})!=nb:raise ValueError('Duplicate bone names')
 events=[]
 for _ in range(ne):
  clip,t,n=struct.unpack_from('>If32s',raw,offset);offset+=40
  if clip>=nc or not math.isfinite(t) or t<0 or t>clips[clip]['count']/clips[clip]['fps']:raise ValueError('Invalid animation event')
  events.append(dict(clip=clips[clip]['name'],time=t,name=name(n)))
 if any(x[0]>=nv for x in struct.iter_unpack('>H',raw[offset:offset+2*ni])):raise ValueError('Skeletal index out of bounds')
 offset+=2*ni
 for _ in range(nv):
  v=struct.unpack_from('>8f4H4f',raw,offset);offset+=56
  if any(not math.isfinite(x) for x in v[:8]+v[12:]) or any(abs(x)>100 for x in v[:3]) or any(abs(x)>2 for x in v[3:6]) or any(x>=nb for x in v[8:12]) or any(x<0 or x>1 for x in v[12:]) or abs(sum(v[12:])-1)>.001:raise ValueError('Invalid skeletal vertex/weights')
 for values in struct.iter_unpack('>10f',raw[offset:]):
  if any(not math.isfinite(x) for x in values) or any(abs(x)>1000 for x in values[:3]) or abs(sum(x*x for x in values[3:7])-1)>.003 or any(not .0001<=x<=100 for x in values[7:]):raise ValueError('Invalid bone TRS key')
 return dict(format=2,vertices=nv,triangles=ni//3,frames=nf,clips=clips,bytes=len(raw),bones=bones,events=events,groups=ng,animationBytes=nb*nf*40)

def write(vertices,indices,groups,bones,clips,events=()):
 """Clips contain name/fps/loop and frames shaped [frame,bone,TRS10]."""
 out=bytearray(struct.pack('>12I',MAGIC,2,len(vertices),len(indices),len(groups),len(clips),sum(len(c['frames']) for c in clips),56,len(bones),len(events),0,0))
 for g in groups:out.extend(struct.pack('>II3fI',*g))
 first=0
 for c in clips:
  out.extend(struct.pack('>32sIIfI',c['name'].encode(),first,len(c['frames']),c['fps'],int(c.get('loop',True))));first+=len(c['frames'])
 for b in bones:out.extend(struct.pack('>32si16f',b['name'].encode(),b['parent'],*b['inverseBind']))
 names=[c['name'] for c in clips]
 for e in events:out.extend(struct.pack('>If32s',names.index(e['clip']),e['time'],e['name'].encode()))
 out.extend(struct.pack('>'+str(len(indices))+'H',*indices))
 for v in vertices:out.extend(struct.pack('>8f4H4f',*v))
 for c in clips:
  for frame in c['frames']:
   for key in frame:out.extend(struct.pack('>10f',*key))
 inspect(out);return bytes(out)
