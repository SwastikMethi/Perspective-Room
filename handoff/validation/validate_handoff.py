"""Validate this documentation package, not the application implementation.

Run: python validation/validate_handoff.py
Requires PyYAML. Uses a deliberately small instance checker covering the schema
keywords used by this package; it is not a full JSON Schema/OpenAPI conformance tool.
"""
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime
import json
import math
import re
import uuid
import yaml

ROOT = Path(__file__).resolve().parents[1]
checks=[]
def require(condition, message):
    if not condition: raise AssertionError(message)
    checks.append(message)
def read(path):return json.loads((ROOT/path).read_text())
def resolve(doc, ref):
    require(ref.startswith('#/'),'Local reference: '+ref)
    value=doc
    for key in ref[2:].split('/'):
        value=value[key.replace('~1','/').replace('~0','~')]
    return value
def schema_walk(value,root):
    if isinstance(value,dict):
        if '$ref' in value:resolve(root,value['$ref'])
        if value.get('type')=='object' and 'properties' in value:
            require(set(value.get('required',[])) <= set(value['properties']), 'Required fields exist in object properties')
        for item in value.values():schema_walk(item,root)
    elif isinstance(value,list):
        for item in value:schema_walk(item,root)
def instance(value,schema,root,path='$'):
    if '$ref' in schema:return instance(value,resolve(root,schema['$ref']),root,path)
    if 'anyOf' in schema:
        ok=False
        for sub in schema['anyOf']:
            try:instance(value,sub,root,path);ok=True;break
            except (AssertionError,ValueError):pass
        assert ok, f'{path}: no anyOf option matches'
        return
    kinds=schema.get('type');kinds=[kinds] if isinstance(kinds,str) else kinds
    predicates={'null':lambda x:x is None,'string':lambda x:isinstance(x,str),'boolean':lambda x:isinstance(x,bool),'integer':lambda x:isinstance(x,int) and not isinstance(x,bool),'number':lambda x:isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x),'object':lambda x:isinstance(x,dict),'array':lambda x:isinstance(x,list)}
    if kinds:assert any(predicates[k](value) for k in kinds),f'{path}: wrong type'
    if 'enum' in schema:assert value in schema['enum'],f'{path}: invalid enum'
    if isinstance(value,dict):
        props=schema.get('properties',{})
        assert set(schema.get('required',[])) <= set(value),f'{path}: missing required field'
        if schema.get('additionalProperties') is False:assert set(value)<=set(props),f'{path}: extra fields'
        for k,v in value.items():
            if k in props:instance(v,props[k],root,path+'.'+k)
    if isinstance(value,list):
        assert len(value)>=schema.get('minItems',0),f'{path}: too few items'
        assert len(value)<=schema.get('maxItems',10**9),f'{path}: too many items'
        if schema.get('uniqueItems'):assert len({json.dumps(x,sort_keys=True) for x in value})==len(value),f'{path}: duplicate item'
        for n,v in enumerate(value):instance(v,schema.get('items',{}),root,f'{path}[{n}]')
    if isinstance(value,str):
        assert len(value)>=schema.get('minLength',0),f'{path}: too short'
        assert len(value)<=schema.get('maxLength',10**9),f'{path}: too long'
        if schema.get('format')=='uuid':uuid.UUID(value)
        if schema.get('format')=='date-time':datetime.fromisoformat(value.replace('Z','+00:00'))
        if schema.get('format')=='uri':assert urlsplit(value).scheme,f'{path}: URI lacks scheme'
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        assert value>=schema.get('minimum',-math.inf),f'{path}: below minimum'
        assert value<=schema.get('maximum',math.inf),f'{path}: above maximum'

json_files=list(ROOT.rglob('*.json'))
for file in json_files:json.loads(file.read_text())
require(True,f'{len(json_files)} JSON files parse')
api=yaml.safe_load((ROOT/'contracts/openapi.yaml').read_text())
require(api['openapi']=='3.1.0','OpenAPI version is 3.1.0')
schema_walk(api,api)
operations=[]
for path,methods in api['paths'].items():
    for method,operation in methods.items():
        operations.append(operation['operationId'])
        names=set(re.findall(r'\{(.*?)\}',path))
        params={p['name'] for p in operation.get('parameters',[]) if p['in']=='path' and p.get('required')}
        require(names==params,'Path parameters match '+operation['operationId'])
        require(bool(operation['responses']),'Responses exist for '+operation['operationId'])
require(len(operations)==len(set(operations)),'Operation IDs are unique')
mirror=read('contracts/domain.schema.json')
require(mirror['components']==api['components'],'Domain mirror matches OpenAPI')

for name in ['intake','contribution','summary','memory','research']:
    s=read(f'contracts/llm/{name}.schema.json')
    schema_walk(s,s)
    public={k:v for k,v in s.items() if k not in ['$schema','title']}
    require(public==api['components']['schemas'][name.title()],name+' schema matches public component')
    instance(read(f'fixtures/{name}.example.json'),s,s)
    require(True,name+' fixture matches implemented schema keywords')
    def strict(v):
        if isinstance(v,dict):
            if v.get('type')=='object':
                assert v.get('additionalProperties') is False
                assert set(v['required'])==set(v['properties'])
            for i in v.values():strict(i)
        elif isinstance(v,list):
            for i in v:strict(i)
    strict(s)

for filename,component in [('api.session.example','Session'),('api.turn.request','TurnCreate'),('api.message.example','Message'),('api.run-event.example','RunEvent'),('api.folder.example','Folder'),('api.organization.request','SessionOrganizationPatch'),('api.session-list.example','SessionList'),('api.fork.request','ForkCreate'),('api.fork-result.example','ForkResult')]:
    instance(read(f'fixtures/{filename}.json'),api['components']['schemas'][component],api)
    require(True,filename+' validates against '+component)

ps=read('config/personalities.json'); ids={p['id'] for p in ps['personas']}
require(len(ps['personas'])==len(ids)==8,'Exactly eight unique personalities')
require(set(ps['default_selection'])<=ids,'Default profiles exist')
for p in ps['personas']:instance(p,api['components']['schemas']['Persona'],api)
cases=read('fixtures/benchmark_cases.json')['cases']
require(len(cases)==len({c['id'] for c in cases})==30,'Exactly thirty unique benchmark cases')
for c in cases:
    instance(c,api['components']['schemas']['EvaluationCase'],api)
    assert len(c['user_turns'])==3 and set(c['persona_ids'])<=ids
require(True,'Every benchmark case has three turns and valid profiles')

req=read('fixtures/jev.route.request.json');resp=read('fixtures/jev.route.response.json')
require(set(req['questions'])==set(resp['answers']),'Jev response covers all requested questions')
for key,q in req['questions'].items():
    a=resp['answers'][key]; probs=a['probabilities']
    assert set(probs)==set(q['criteria']) and a['choice'] in probs
    assert all(0<=v<=1 for v in probs.values()) and math.isclose(sum(probs.values()),1,abs_tol=1e-6)
    n=len(probs); expected=(max(probs.values())-1/n)/(1-1/n)
    assert math.isclose(a['confidence'],expected,abs_tol=1e-6)
require(True,'Jev fixture probabilities and confidence are consistent')

pack=read('fixtures/research_pack.json')
for source in pack['sources']:instance(source,api['components']['schemas']['Source'],api)
source_ids={s['id'] for s in pack['sources']}
for finding in pack['normalized']['findings']:assert set(finding['source_ids'])<=source_ids
demo=read('fixtures/demo_session.json'); message_ids={m['id'] for m in demo['messages']}
for m in demo['messages']:instance(m,api['components']['schemas']['Message'],api)
for section in demo['summary']['sections']:
    for it in section['items']:assert set(it['source_message_ids'])<=message_ids
require(True,'Demo and research fixture references resolve')

# Verify new workspace contracts and the approved UI reference/config relationship.
instance(demo['session'],api['components']['schemas']['Session'],api)
workspace=read('fixtures/workspace.example.json')
assert workspace['is_fixture'] is True
instance(workspace['folders'],api['components']['schemas']['FolderList'],api)
for name in ['active_chats','archived_chats']:
    instance(workspace[name],api['components']['schemas']['SessionList'],api)
folders={f['id']:f for f in workspace['folders']['items']}
chats=workspace['active_chats']['items']+workspace['archived_chats']['items']
assert len({c['id'] for c in chats})==len(chats)
for c in chats:assert c['folder_id'] is None or c['folder_id'] in folders
for f in folders.values():
    assert f['chat_count']==sum(c['folder_id']==f['id'] and not c['is_archived'] for c in chats)
    assert f['archived_chat_count']==sum(c['folder_id']==f['id'] and c['is_archived'] for c in chats)
assert set(workspace['drafts']) <= {c['id'] for c in chats}
assert set(workspace['ui_state']['open_folder_ids']) <= set(folders)
require(True,'Workspace fixture schemas, membership, counts and separate draft keys agree')
search=read('fixtures/api.session-list.example.json')['items'][0]
match=search['match']; by_id={m['id']:m for m in demo['messages']}
assert match['message_id'] in by_id
assert match['message_sequence']==by_id[match['message_id']]['sequence']
assert match['snippet'] in by_id[match['message_id']]['text']
require(True,'Search hit deep link resolves to the example transcript')
fork=read('fixtures/api.fork.request.json'); result=read('fixtures/api.fork-result.example.json')
assert fork['before_message_id'] in by_id and by_id[fork['before_message_id']]['role']=='user'
assert fork['through_message_id'] is None and fork['purpose']=='edit'
assert result['session']['id'] != demo['session']['id']
assert result['session']['origin_session_id']==demo['session']['id']
assert result['turn_template']['expected_version']==result['session']['version']
require(True,'Edit branch fixture keeps origin and new-session version coherent')
ui=read('config/persona-ui.json'); tokens=read('config/design-tokens.json'); defaults=read('config/app.defaults.json')
assert len(ui['personas'])==8 and set(ui['order'])==ids
assert [p['persona_id'] for p in ui['personas']]==ui['order']
assert tokens['default_theme']==defaults['ui']['default_theme']=='dark'
assert set(tokens['themes'])==set(defaults['ui']['theme_options'])=={'dark','light'}
assert set(tokens['themes']['dark'])==set(tokens['themes']['light'])
assert tokens['layout_px']['sidebar_collapsed']==defaults['ui']['sidebar_collapsed_width_px']==64
assert tokens['layout_px']['sidebar_expanded']==defaults['ui']['sidebar_expanded_width_px']==272
for filename in ['approved-room-dark.png','approved-room-light.png','sidebar-expanded-dark.png','sidebar-expanded-light.png']:
    payload=(ROOT/'ui'/filename).read_bytes()
    assert payload[:8]==b'\x89PNG\r\n\x1a\n'
    width,height=int.from_bytes(payload[16:20],'big'),int.from_bytes(payload[20:24],'big')
    assert width>=1400 and height>=800
    if filename.startswith('approved'):assert [width,height]==ui['source_size_px']
for persona in ui['personas']:
    r=persona['source_rect_px'];w,h=ui['source_size_px']
    assert 0<=r['x']<r['x']+r['width']<=w and 0<=r['y']<r['y']+r['height']<=h
for path in ui['source_images'].values():assert (ROOT/path).is_file()
assert not (ROOT/'ui/room-reference.png').exists() and not (ROOT/'ui/room-reference.svg').exists()
require(True,'Eight persona mappings, both themes, sidebar tokens and four UI images agree')

def luminance(color):
    values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    values=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in values]
    return sum(v*w for v,w in zip(values,(0.2126,0.7152,0.0722)))
def contrast(a,b):
    low,high=sorted((luminance(a),luminance(b)))
    return (high+0.05)/(low+0.05)
for theme in tokens['themes'].values():
    for foreground,background in [('text','canvas'),('muted','canvas'),('muted','surface'),('on_accent','accent')]:
        assert contrast(theme[foreground],theme[background])>=4.5
    assert contrast(theme['focus'],theme['canvas'])>=3
require(True,'Core theme text pairs meet 4.5:1 and focus pairs meet 3:1; rendered app still needs accessibility checks')

link_count=0
for file in ROOT.rglob('*.md'):
    for target in re.findall(r'\]\(([^)]+)\)',file.read_text()):
        if target.startswith(('http://','https://','#','mailto:')):continue
        destination=(file.parent/target.split('#')[0]).resolve()
        assert destination.exists(),f'Broken link {file.name}: {target}'
        link_count+=1
require(True,f'{link_count} local Markdown links resolve')
env=(ROOT/'config/env.example').read_text()
assert re.search(r'^OPENAI_API_KEY=$',env,re.M) and re.search(r'^TYPESAFE_API_KEY=$',env,re.M)
require(read('config/app.defaults.json')['limits']['session_usd_cap'] is None,'No default dollar cap')
require(True,'Credential placeholders are empty')

report={'package_version':api['info']['version'],'status':'passed','checks':len(checks),'json_files':len(json_files),'openapi_paths':len(api['paths']),'operations':len(operations),'personalities':len(ids),'benchmark_cases':len(cases),'local_links':link_count,'ui_references':4,'themes':['dark','light'],'scope':'Syntax, local references, internal contract relationships, fixture types/bounds/formats, workspace relationships, UI asset/config relationships, counts, and configuration. Not a complete JSON Schema/OpenAPI standards certification or an application/live-provider test.'}
print(json.dumps(report,indent=2))
