"""Local glTF 2 binary importer. Data only: no Blender, network or script execution.

Supported: one skin, four weights, triangle primitives, embedded base-color images,
TRS/node animation, LINEAR/STEP/CUBICSPLINE. Explicitly reject unsupported features.
"""
import base64,json,math,re,struct,uuid
import numpy as np
import skeletal_asset,material_library

def compose(v):
 t,q,s=np.array(v[:3]),np.array(v[3:7]),np.array(v[7:]);x,y,z,w=q
 r=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
 m=np.eye(4);m[:3,:3]=r*s;m[:3,3]=t;return m

def decompose(m):
 s=np.linalg.norm(m[:3,:3],axis=0)
 if np.any(s<.0001) or np.linalg.det(m[:3,:3])<=0:raise ValueError('GLB: mirrored or zero-scale nodes are unsupported')
 r=m[:3,:3]/s
 if not np.allclose(r.T@r,np.eye(3),atol=1e-4):raise ValueError('GLB: node matrix contains shear')
 trace=np.trace(r)
 if trace>0:
  d=math.sqrt(trace+1)*2;q=[(r[2,1]-r[1,2])/d,(r[0,2]-r[2,0])/d,(r[1,0]-r[0,1])/d,d/4]
 else:
  i=int(np.argmax(np.diag(r)));j=(i+1)%3;k=(i+2)%3;d=math.sqrt(1+r[i,i]-r[j,j]-r[k,k])*2;q=[0.,0.,0.,(r[k,j]-r[j,k])/d];q[i]=d/4;q[j]=(r[i,j]+r[j,i])/d;q[k]=(r[i,k]+r[k,i])/d
 return [*m[:3,3],*q,*s]

def convert(raw):
 if len(raw)<20 or len(raw)>100*1024*1024:raise ValueError('GLB: file size out of range')
 magic,version,size=struct.unpack_from('<III',raw)
 if magic!=0x46546c67 or version!=2 or size!=len(raw):raise ValueError('GLB: invalid version/header')
 chunks={};p=12
 while p<len(raw):
  if p+8>len(raw):raise ValueError('GLB: truncated chunk')
  count,kind=struct.unpack_from('<II',raw,p);p+=8
  if count%4 or p+count>len(raw) or kind in chunks:raise ValueError('GLB: invalid chunks')
  chunks[kind]=raw[p:p+count];p+=count
 doc=json.loads(chunks[0x4e4f534a]);blob=chunks.get(0x004e4942,b'')
 if doc.get('asset',{}).get('version')!='2.0' or doc.get('extensionsRequired'):raise ValueError('GLB: use uncompressed glTF 2.0 without required extensions')
 buffers=doc.get('buffers',[])
 if len(buffers)!=1 or buffers[0].get('uri') or buffers[0]['byteLength']>len(blob):raise ValueError('GLB: embed all buffers in the file')
 def view(index):
  v=doc['bufferViews'][index];start=v.get('byteOffset',0);length=v['byteLength']
  if v.get('buffer',0)!=0 or start<0 or length<0 or start+length>buffers[0]['byteLength']:raise ValueError('GLB: invalid buffer view')
  return memoryview(blob)[start:start+length],v
 def accessor(index):
  a=doc['accessors'][index]
  if a.get('sparse'):raise ValueError('GLB: sparse accessors are unsupported; export dense data')
  dtype={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']];dtype=np.dtype(dtype);width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];count=a['count']
  if type(count)!=int or not 0<count<=1000000:raise ValueError('GLB: accessor exceeds budget')
  data,v=view(a['bufferView']);offset=a.get('byteOffset',0);stride=v.get('byteStride',width*dtype.itemsize)
  if offset<0 or stride<width*dtype.itemsize or offset+(count-1)*stride+width*dtype.itemsize>len(data):raise ValueError('GLB: accessor bounds')
  result=np.ndarray((count,width),dtype=dtype,buffer=data,offset=offset,strides=(stride,dtype.itemsize)).astype(float)
  if a.get('normalized') and dtype.kind in 'iu':result=np.maximum(-1,result/np.iinfo(dtype).max)
  if not np.isfinite(result).all():raise ValueError('GLB: non-finite accessor')
  return result
 nodes=doc.get('nodes',[])
 if not nodes or len(nodes)>128:raise ValueError('GLB: use 1–128 nodes/bones')
 parents=[-1]*len(nodes)
 for i,n in enumerate(nodes):
  for child in n.get('children',[]):
   if type(child)!=int or not 0<=child<len(nodes) or parents[child]!=-1:raise ValueError('GLB: invalid/shared node parent')
   parents[child]=i
 order=[];visiting=set()
 def visit(i):
  if i in visiting:raise ValueError('GLB: cyclic node hierarchy')
  if i in order:return
  visiting.add(i)
  if parents[i]>=0:visit(parents[i])
  visiting.remove(i);order.append(i)
 for i in range(len(nodes)):visit(i)
 remap={old:new for new,old in enumerate(order)}
 rest=[];globals=[];used=set();bones=[]
 for old in order:
  n=nodes[old];trs=decompose(np.array(n['matrix'],dtype=float).reshape(4,4).T) if 'matrix'in n else n.get('translation',[0,0,0])+n.get('rotation',[0,0,0,1])+n.get('scale',[1,1,1])
  if len(trs)!=10 or not np.isfinite(trs).all() or abs(np.linalg.norm(trs[3:7])-1)>.003:raise ValueError('GLB: invalid node transform')
  rest.append(trs);parent=remap[parents[old]] if parents[old]>=0 else -1;global_m=compose(trs) if parent<0 else globals[parent]@compose(trs);globals.append(global_m)
  name=re.sub('[^A-Za-z0-9_-]','_',n.get('name','Bone_'+str(old)))[:24] or 'Bone';base=name;number=1
  while name in used:name=base+'_'+str(number);number+=1
  used.add(name);bones.append(dict(name=name,parent=parent,inverseBind=np.linalg.inv(global_m).ravel().tolist()))
 skins=doc.get('skins',[])
 if len(skins)>1:raise ValueError('GLB: combine meshes into one skin before import')
 if skins:
  skin=skins[0];joints=skin['joints']
  if len(set(joints))!=len(joints) or any(j not in remap for j in joints):raise ValueError('GLB: invalid skin joints')
  matrices=accessor(skin['inverseBindMatrices']) if 'inverseBindMatrices'in skin else np.tile(np.eye(4).T.ravel(),(len(joints),1))
  if matrices.shape!=(len(joints),16):raise ValueError('GLB: inverse bind count')
  for node,m in zip(joints,matrices):bones[remap[node]]['inverseBind']=m.reshape(4,4).T.ravel().tolist()
 # Only geometry reachable from the selected scene is imported.
 roots=doc.get('scenes',[{}])[doc.get('scene',0)].get('nodes',[i for i,p in enumerate(parents) if p<0]);active=set()
 def include(i):
  if i in active:return
  active.add(i)
  for child in nodes[i].get('children',[]):include(child)
 for i in roots:include(i)
 vertices=[];indices=[];groups=[];slots=[];materials={};textures={};files={};material_map={};image_map={}
 def material(index):
  if index in material_map:return material_map[index]
  m=doc.get('materials',[])[index] if index>=0 else {};pbr=m.get('pbrMetallicRoughness',{});color=pbr.get('baseColorFactor',[1,1,1,1]);mode=m.get('alphaMode','OPAQUE')
  if mode not in ('OPAQUE','MASK'):raise ValueError('GLB: use opaque or alpha-mask materials; alpha blending is unsupported')
  texture='';tex=pbr.get('baseColorTexture')
  if tex:
   if tex.get('texCoord',0)!=0 or tex.get('extensions'):raise ValueError('GLB: use untransformed TEXCOORD_0')
   image_index=doc['textures'][tex['index']]['source']
   if image_index not in image_map:
    image=doc['images'][image_index]
    if 'bufferView'in image:payload=bytes(view(image['bufferView'])[0])
    elif image.get('uri','').startswith(('data:image/png;base64,','data:image/jpeg;base64,')):payload=base64.b64decode(image['uri'].split(',',1)[1],validate=True)
    else:raise ValueError('GLB: embed PNG/JPEG images; external files are unsupported')
    tid=uuid.uuid4().hex[:12];meta,png=material_library.convert(payload,tid);textures[tid]=meta;files['textures/'+tid+'.png']=png;image_map[image_index]=tid
   texture=image_map[image_index]
  mid=uuid.uuid4().hex[:12];materials[mid]=dict(name=str(m.get('name','Material '+str(index)))[:60],color=list(color[:3]),texture=texture,alphaMode='cutout' if mode=='MASK' else 'opaque',alphaCutoff=m.get('alphaCutoff',.5));material_map[index]=mid;return mid
 for old in order:
  n=nodes[old]
  if old not in active or 'mesh'not in n:continue
  for primitive in doc['meshes'][n['mesh']]['primitives']:
   attrs=primitive['attributes']
   if primitive.get('mode',4)!=4 or primitive.get('targets') or 'JOINTS_1'in attrs or 'COLOR_0'in attrs:raise ValueError('GLB: use triangles, no morph targets/vertex colors, at most four weights')
   position=accessor(attrs['POSITION']);count=len(position)
   if position.shape!=(count,3):raise ValueError('GLB: invalid position shape')
   normal=accessor(attrs['NORMAL']) if 'NORMAL'in attrs else np.zeros_like(position);uv=accessor(attrs['TEXCOORD_0']) if 'TEXCOORD_0'in attrs else np.zeros((count,2))
   idx=accessor(primitive['indices']).reshape(-1) if 'indices'in primitive else np.arange(count)
   if len(idx)%3 or np.any(idx<0) or np.any(idx>=count) or np.any(idx!=np.floor(idx)):raise ValueError('GLB: invalid triangle indices')
   idx=idx.astype(int)
   if 'NORMAL'not in attrs:
    for a,b,c in idx.reshape(-1,3):
     cross=np.cross(position[b]-position[a],position[c]-position[a]);normal[a]+=cross;normal[b]+=cross;normal[c]+=cross
   normal/=np.maximum(1e-12,np.linalg.norm(normal,axis=1))[:,None]
   if normal.shape!=(count,3) or uv.shape!=(count,2):raise ValueError('GLB: mismatched vertex attributes')
   if 'skin'in n:
    if n['skin']!=0 or not skins:raise ValueError('GLB: missing skin')
    joint_values=accessor(attrs['JOINTS_0']);weights=accessor(attrs['WEIGHTS_0'])
    if joint_values.shape!=(count,4) or weights.shape!=(count,4) or np.any(joint_values<0) or np.any(joint_values>=len(joints)) or np.any(joint_values!=np.floor(joint_values)) or np.any(weights<0):raise ValueError('GLB: invalid skin weights/joints')
    sums=weights.sum(axis=1)
    if np.any(sums<1e-8):raise ValueError('GLB: zero vertex weights')
    weights/=sums[:,None];joint_values=np.array([[remap[joints[int(j)]] for j in row] for row in joint_values])
   else:
    if skins and old in joints:raise ValueError('GLB: rigid geometry on a skin joint requires a separate node')
    transform=globals[remap[old]];position=(np.c_[position,np.ones(count)]@transform.T)[:,:3];normal=normal@np.linalg.inv(transform[:3,:3]);normal/=np.maximum(1e-12,np.linalg.norm(normal,axis=1))[:,None];joint_values=np.full((count,4),remap[old]);weights=np.tile([1,0,0,0],(count,1))
   if len(vertices)+count>20000:raise ValueError('GLB: exceeds 20,000 vertices; optimize the mesh first')
   start=len(indices);indices.extend((idx+len(vertices)).tolist());vertices.extend([*p,*norm,*tex,*map(int,js),*ws] for p,norm,tex,js,ws in zip(position,normal,uv,joint_values,weights));groups.append((start,len(idx),1,1,1,0));slots.append(material(primitive.get('material',-1)))
 clips=[];names=set();rest=np.array(rest,dtype=float)
 for ai,animation in enumerate(doc.get('animations',[])):
  tracks=[];duration=0;seen=set()
  for channel in animation.get('channels',[]):
   target=channel['target'];node=remap[target['node']];path=target['path'];sampler=animation['samplers'][channel['sampler']];mode=sampler.get('interpolation','LINEAR')
   if path not in ('translation','rotation','scale') or mode not in ('LINEAR','STEP','CUBICSPLINE'):raise ValueError('GLB: unsupported animation channel')
   if (node,path)in seen:raise ValueError('GLB: duplicate animation channel')
   seen.add((node,path));times=accessor(sampler['input']).reshape(-1);values=accessor(sampler['output']);width=4 if path=='rotation' else 3
   if np.any(times<0) or np.any(np.diff(times)<=0) or values.shape!=(len(times)*(3 if mode=='CUBICSPLINE' else 1),width):raise ValueError('GLB: invalid animation sampler')
   duration=max(duration,float(times[-1]));tracks.append((node,path,mode,times,values))
  count=max(1,int(math.ceil(duration*30))+1)
  if count+sum(len(c['frames']) for c in clips)>4096:raise ValueError('GLB: exceeds 4,096 total key frames at 30 fps; split animation files')
  frames=[]
  for frame in range(count):
   keys=rest.copy();time=min(frame/30,duration)
   for node,path,mode,times,values in tracks:
    a=max(0,min(len(times)-1,int(np.searchsorted(times,time,side='right')-1)));b=min(a+1,len(times)-1);dt=times[b]-times[a];t=0 if dt==0 else max(0,min(1,(time-times[a])/dt))
    if mode=='CUBICSPLINE':value=(2*t**3-3*t*t+1)*values[a*3+1]+(t**3-2*t*t+t)*dt*values[a*3+2]+(-2*t**3+3*t*t)*values[b*3+1]+(t**3-t*t)*dt*values[b*3]
    else:
     left=values[a];right=values[b];t=0 if mode=='STEP' else t
     if path=='rotation' and np.dot(left,right)<0:right=-right
     if path=='rotation' and mode=='LINEAR' and abs(np.dot(left,right))<.9995:
      angle=math.acos(float(np.clip(np.dot(left,right),-1,1)));value=(math.sin((1-t)*angle)*left+math.sin(t*angle)*right)/math.sin(angle)
     else:value=left+(right-left)*t
    if path=='rotation':
     length=np.linalg.norm(value)
     if length<1e-8:raise ValueError('GLB: zero animation quaternion')
     value=value/length
    start,end={'translation':(0,3),'rotation':(3,7),'scale':(7,10)}[path];keys[node,start:end]=value
   frames.append(keys.tolist())
  name=re.sub('[^A-Za-z0-9_-]','_',animation.get('name','Animation_'+str(ai)))[:24] or 'Animation';base=name;i=1
  while name in names:name=base+'_'+str(i);i+=1
  names.add(name);clips.append(dict(name=name,fps=30,loop=True,frames=frames))
 if not clips:clips=[dict(name='Idle',fps=30,loop=True,frames=[rest.tolist()])]
 model=skeletal_asset.write(vertices,indices,groups,bones,clips);material_library.validate(dict(materials=materials,textures=textures))
 return dict(model=model,materials=materials,textures=textures,files=files,defaultMaterials=slots)
