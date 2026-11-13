"""Versioned project boundary. Components on disk; legacy runtime adapter in memory.

No files are changed during decoding. Native source projects retain their format.
"""
import copy

FORMAT_VERSION = 4
COMPONENTS = {'Transform', 'MeshRenderer', 'Animator', 'Script', 'Scripts', 'BoxCollider', 'RigidBody', 'Engine'}
ENTITY_FIELDS = {'position', 'rotation', 'scale', 'kind', 'color', 'asset', 'clip',
                 'script', 'scripts', 'collider', 'gravity', 'engine'}


def entity_scripts(e):
    items=e.get('scripts')
    if items is None: return [{'name': e['script'], 'enabled': True}] if e.get('script') else []
    if not isinstance(items,list) or len(items)>16: raise ValueError('An object supports up to 16 script attachments')
    seen=set()
    for item in items:
        if (not isinstance(item,dict) or set(item)!={'name','enabled'} or
            not isinstance(item['name'],str) or not item['name'] or type(item['enabled']) is not bool):
            raise ValueError('Invalid script attachment')
        if item['name'] in seen: raise ValueError('A script can only be attached once per object')
        seen.add(item['name'])
    if e.get('script'): raise ValueError('Use either script or scripts, not both')
    return items


def decode_project(value):
    if not isinstance(value, dict):
        raise ValueError('Project must be a JSON object')
    p = copy.deepcopy(value)
    version = p.get('formatVersion', 1)
    if type(version) is not int or version not in (1, 2, 3, FORMAT_VERSION):
        raise ValueError('Unsupported project format version: ' + str(version))
    if p.get('nativeProject'):
        if version != 1:
            raise ValueError('Native projects keep their original format')
        return p
    if version == 1:
        return p
    for scene in p.get('scenes', []):
        for e in scene.get('entities', []):
            if not isinstance(e, dict) or ENTITY_FIELDS.intersection(e):
                raise ValueError('Format 2: object properties must use components')
            c = e.pop('components', None)
            if not isinstance(c, dict) or set(c) - COMPONENTS:
                raise ValueError('Unsupported component')
            if (version==2 and 'Scripts' in c) or (version>=3 and 'Script' in c) or (version<4 and 'Engine' in c):
                raise ValueError('Script component does not match the project format version')
            if not {'Transform', 'MeshRenderer'} <= set(c):
                raise ValueError('Transform and MeshRenderer are required')
            keys = {'Transform': {'position', 'rotation', 'scale'},
                    'MeshRenderer': {'kind', 'color', 'asset'}, 'Animator': {'clip'},
                    'Script': {'name'}, 'Scripts': {'items'}, 'BoxCollider': set(), 'RigidBody': {'useGravity'}, 'Engine': {'items'}}
            for name, fields in keys.items():
                if name in c and (not isinstance(c[name], dict) or set(c[name]) != fields):
                    raise ValueError('Invalid component properties: ' + name)
            t, m = c['Transform'], c['MeshRenderer']
            if m['kind'] not in ('cube', 'model'):
                raise ValueError('Unsupported renderer type')
            if not isinstance(m['asset'], str) or (m['kind'] == 'cube' and m['asset']):
                raise ValueError('Invalid renderer asset')
            if ('Animator' in c) != (m['kind'] == 'model'):
                raise ValueError('Animator is required only for models')
            if 'Script' in c and (not isinstance(c['Script']['name'], str) or not c['Script']['name']):
                raise ValueError('Select a valid script')
            if 'RigidBody' in c and c['RigidBody']['useGravity'] is not True:
                raise ValueError('This version supports only bodies with gravity')
            if 'Animator' in c and not isinstance(c['Animator']['clip'], str):
                raise ValueError('Invalid animation clip')
            e.update(position=t['position'], rotation=t['rotation'], scale=t['scale'],
                     kind=m['kind'], color=m['color'], asset=m['asset'],
                     clip=c.get('Animator', {}).get('clip', 'Idle'),
                     script=c.get('Script', {}).get('name', ''),
                     collider='BoxCollider' in c, gravity='RigidBody' in c)
            if version>=3:
                items=entity_scripts({'scripts':c.get('Scripts',{}).get('items',[])})
                if len(items)==1 and items[0]['enabled']: e['script']=items[0]['name']
                elif items: e['scripts']=items
            if 'Engine' in c:e['engine']=c['Engine']['items']
    # In-memory entities use the existing runtime representation, never a hybrid.
    p.pop('formatVersion', None)
    return p


def encode_project(value):
    p = decode_project(value)
    if p.get('nativeProject'):
        return p
    extended=bool(p.get('materials') or p.get('textures') or any(a.get('format')==2 for a in p.get('assets',{}).values()) or any(e.get('engine') for s in p.get('scenes',[]) for e in s['entities']))
    for scene in p.get('scenes', []):
        for e in scene.get('entities', []):
            c = {'Transform': {k: e[k] for k in ('position', 'rotation', 'scale')},
                 'MeshRenderer': {k: e[k] for k in ('kind', 'color', 'asset')}}
            if e['kind'] == 'model': c['Animator'] = {'clip': e['clip']}
            items=entity_scripts(e)
            if items: c['Scripts'] = {'items': copy.deepcopy(items)}
            if e['collider']: c['BoxCollider'] = {}
            if e['gravity']: c['RigidBody'] = {'useGravity': True}
            if e.get('engine'):c['Engine']={'items':copy.deepcopy(e['engine'])}
            for key in ENTITY_FIELDS: e.pop(key, None)
            e['components'] = c
    p['formatVersion'] = 4 if extended else 3
    return p
