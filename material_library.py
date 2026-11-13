"""Independent project textures and per-renderer material slots (opaque/cutout)."""
import hashlib,io,math,re
from pathlib import Path
from PIL import Image
ID=re.compile(r'^[a-f0-9]{12}$')
def validate(p):
 textures=p.get('textures',{});materials=p.get('materials',{})
 if not isinstance(textures,dict) or len(textures)>8 or not isinstance(materials,dict) or len(materials)>32:raise ValueError('Use up to 8 project textures and 32 materials')
 for tid,t in textures.items():
  if not ID.fullmatch(tid) or not isinstance(t,dict) or set(t)-{'file','size','sha256','name'} or not {'file','size','sha256'}<=set(t) or t['file']!=tid+'.png' or type(t['size']) is not int or t['size'] not in (128,256,512,1024) or not isinstance(t['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',t['sha256']) or ('name'in t and (not isinstance(t['name'],str) or len(t['name'])>60)):raise ValueError('Invalid project texture metadata')
 for mid,m in materials.items():
  if not ID.fullmatch(mid) or not isinstance(m,dict) or set(m)!={'name','color','texture','alphaMode','alphaCutoff'} or not isinstance(m['name'],str) or not 1<=len(m['name'])<=60:raise ValueError('Invalid material')
  if not isinstance(m['color'],list) or len(m['color'])!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in m['color']):raise ValueError(m['name']+': invalid color')
  if m['texture'] and m['texture'] not in textures:raise ValueError(m['name']+': missing texture')
  if m['alphaMode'] not in ('opaque','cutout') or type(m['alphaCutoff']) not in (int,float) or not math.isfinite(m['alphaCutoff']) or not 0<=m['alphaCutoff']<=1:raise ValueError(m['name']+': invalid opacity mode/cutoff')
 variants={variant(m) for m in materials.values() if m['texture']}
 if sum(textures[x[0]]['size']**2*4 for x in variants)>32*1024*1024:raise ValueError('Material variants exceed the 32 MiB GPU texture budget')

def variant(m):return (m['texture'],m['alphaMode'],round(m['alphaCutoff'],4) if m['alphaMode']=='cutout' else 0)
def read(root,tid,meta):
 raw=(Path(root)/'textures'/meta['file']).read_bytes()
 if len(raw)>16*1024*1024 or hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Texture '+tid+': checksum mismatch')
 with Image.open(io.BytesIO(raw)) as image:
  if image.format!='PNG' or image.size!=(meta['size'],meta['size']):raise ValueError('Texture '+tid+': dimensions mismatch')
  image.verify()
 return raw

def current(root,tid):
 if not ID.fullmatch(tid):raise ValueError('Invalid texture ID')
 raw=(Path(root)/'textures'/(tid+'.png')).read_bytes()
 if len(raw)>16*1024*1024:raise ValueError('Texture file exceeds 16 MiB')
 with Image.open(io.BytesIO(raw)) as image:
  if image.format!='PNG' or image.width!=image.height or image.width not in (128,256,512,1024):raise ValueError('Reloaded texture must be a square PNG (128–1024)')
  size=image.width;image.verify()
 return dict(file=tid+'.png',size=size,sha256=hashlib.sha256(raw).hexdigest())

def convert(raw,tid):
 if not ID.fullmatch(tid) or not raw or len(raw)>32*1024*1024:raise ValueError('Invalid texture import')
 with Image.open(io.BytesIO(raw)) as image:
  if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>16*1024*1024:raise ValueError('Use a PNG/JPEG/WebP texture up to 16 megapixels')
  size=min(1024,max(128,2**math.ceil(math.log2(max(image.size)))));image=image.convert('RGBA').resize((size,size),Image.Resampling.LANCZOS);out=io.BytesIO();image.save(out,format='PNG');png=out.getvalue()
 return dict(file=tid+'.png',size=size,sha256=hashlib.sha256(png).hexdigest()),png

def native_indices(p):
 variants=[];bindings={}
 for mid,m in sorted(p.get('materials',{}).items()):
  v=variant(m)
  if not m['texture']:bindings[mid]=-1
  else:
   if v not in variants:variants.append(v)
   bindings[mid]=variants.index(v)
 return variants,bindings

def write_header(p,root,target):
 validate(p);variants,_=native_indices(p)
 with Path(target).open('w',encoding='ascii') as out:
  out.write('#ifndef FORGE_MATERIALS_H\n#define FORGE_MATERIALS_H\n#define FORGE_MATERIAL_COUNT '+str(len(variants))+'\nstruct ForgeMaterialImage{unsigned size;const unsigned short* pixels;};\n')
  entries=[]
  for i,(tid,mode,cutoff) in enumerate(variants):
   meta=p['textures'][tid];raw=read(root,tid,meta)
   with Image.open(io.BytesIO(raw)) as im:image=im.convert('RGBA')
   out.write('static const unsigned short materialPixels'+str(i)+'[]={\n');row=[]
   for r,g,b,a in image.getdata():
    row.append(hex(((1 if mode=='opaque' or a/255.>=cutoff else 0)<<15)|((r>>3)<<10)|((g>>3)<<5)|(b>>3)))
    if len(row)==24:out.write(','.join(row)+',\n');row=[]
   if row:out.write(','.join(row)+',\n')
   out.write('};\n');entries.append('{'+str(meta['size'])+',materialPixels'+str(i)+'}')
  out.write('static const ForgeMaterialImage forgeMaterialImages[]={'+(','.join(entries) if entries else '{0,nullptr}')+'};\n#endif\n')
