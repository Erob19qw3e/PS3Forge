"""Run with Blender, converting one GLB rig (or static meshes) to IYAM."""
import bpy, sys, struct, math
from pathlib import Path
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:]
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=args[0])
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
if not meshes or len(rigs)>1:raise ValueError('GLB files must contain meshes and at most one skeleton')
rig=rigs[0] if rigs else None
actions=list(bpy.data.actions)[:16] if rig else []
if rig:
 rig.animation_data_create()
 for track in rig.animation_data.nla_tracks:track.mute=True
clips=[]
for a in actions:
 name=a.name.rsplit('|',1)[-1].encode('ascii','replace').decode()[:31]
 if any(x[0]==name for x in clips):name='Clip'+str(len(clips))
 clips.append((name,a,int(a.frame_range[0]),int(a.frame_range[1])))
if not clips:clips=[('Idle',None,0,0)]
def update(action,frame):
 if rig:rig.animation_data.action=action
 bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
update(clips[0][1],clips[0][2])
groups={};counts=[];nv=0
for obj in meshes:
 e=obj.evaluated_get(bpy.context.evaluated_depsgraph_get());m=e.to_mesh();m.calc_loop_triangles();counts.append(len(m.vertices))
 for tri in m.loop_triangles:
  key=(obj.name,tri.material_index)
  if key not in groups:
   mat=m.materials[tri.material_index] if m.materials else None;color=tuple(mat.diffuse_color[:3]) if mat else (.7,.7,.7)
   if mat and mat.use_nodes:
    node=mat.node_tree.nodes.get('Principled BSDF')
    if node:color=tuple(node.inputs['Base Color'].default_value[:3])
   groups[key]=[[],tuple(max(0,min(1,float(c))) for c in color)]
  groups[key][0].extend(nv+i for i in tri.vertices)
 nv+=len(m.vertices);e.to_mesh_clear()
if not 0<nv<=20000:raise ValueError('Models support up to 20,000 vertices')
indices=[];gr=[]
for ids,color in groups.values():gr.append((len(indices),len(ids),*color,0));indices.extend(ids)
records=[];cr=[];nf=0
for name,action,start,end in clips:
 count=max(1,end-start+1)
 if nf+count>1000 or (nf+count)*nv*32>64*1024*1024:raise ValueError('Pose budget exceeded: reduce animation length, clips or vertices')
 cr.append((name,nf,count,24.,int(not any(x in name.lower() for x in ('death','attack','jump')))))
 for frame in range(start,end+1):
  update(action,frame);deps=bpy.context.evaluated_depsgraph_get()
  for oi,obj in enumerate(meshes):
   e=obj.evaluated_get(deps);m=e.to_mesh()
   if len(m.vertices)!=counts[oi]:raise ValueError('Animated topology changes are not supported')
   normal=e.matrix_world.to_3x3().inverted().transposed()
   for v in m.vertices:
    co=e.matrix_world@v.co;n=(normal@v.normal).normalized()
    if max(abs(c) for c in co)>100:raise ValueError('Model exceeds 100 units: resize it in the source file')
    records.append(struct.pack('>8f',co.x,co.z,-co.y,n.x,n.z,-n.y,.5,.5))
   e.to_mesh_clear()
  nf+=1
out=Path(args[1])
with out.open('wb') as f:
 f.write(struct.pack('>8I',0x4959414d,1,nv,len(indices),len(gr),len(cr),nf,32))
 for g in gr:f.write(struct.pack('>II3fI',*g))
 for name,first,count,fps,loop in cr:f.write(struct.pack('>32sIIfI',name.encode(),first,count,fps,loop))
 f.write(struct.pack('>'+str(len(indices))+'H',*indices));f.write(b''.join(records))
print('FORGE_CONVERSION_OK',nv,nf)
