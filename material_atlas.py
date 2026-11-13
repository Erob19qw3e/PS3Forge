"""Validated project-local PNG atlas, compiled into the native texture header."""
import hashlib
import io
from pathlib import Path
from PIL import Image

def validate_metadata(meta):
    if not isinstance(meta,dict) or set(meta)!={'file','size','sha256'}:raise ValueError('Invalid material atlas metadata')
    if meta['file']!='atlas.png' or type(meta['size']) is not int or meta['size'] not in (256,512,1024,2048):raise ValueError('Invalid material atlas dimensions')
    if not isinstance(meta['sha256'],str) or len(meta['sha256'])!=64 or any(c not in '0123456789abcdef' for c in meta['sha256']):raise ValueError('Invalid material atlas checksum')

def validate_bytes(raw,meta):
    validate_metadata(meta)
    if len(raw)>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Material atlas checksum mismatch')
    with Image.open(io.BytesIO(raw)) as image:
        if image.format!='PNG' or image.size!=(meta['size'],meta['size']):raise ValueError('Material atlas must be the declared square PNG')
        image.verify()

def read_project(root,meta):
    validate_metadata(meta);raw=(Path(root)/'textures/atlas.png').read_bytes();validate_bytes(raw,meta);return raw

def write_header(root,meta,target):
    raw=read_project(root,meta)
    with Image.open(io.BytesIO(raw)) as image:image=image.convert('RGBA')
    with Path(target).open('w',encoding='ascii') as output:
        output.write('// Project-local source texture, ARGB1555.\n#define FORGE_ATLAS_SIZE '+str(meta['size'])+'\n#define FORGE_ATLAS_ARGB1555 1\nstatic const unsigned short forgeAtlas565[]={\n')
        row=[]
        pixels=image.get_flattened_data() if hasattr(image,'get_flattened_data') else image.getdata()
        for r,g,b,a in pixels:
            row.append(hex(((1 if a>=128 else 0)<<15)|((r>>3)<<10)|((g>>3)<<5)|(b>>3)))
            if len(row)==24:output.write(','.join(row)+',\n');row=[]
        if row:output.write(','.join(row)+',\n')
        output.write('};\n')
