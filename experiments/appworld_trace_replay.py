"""Resolve protected AppWorld HTTP traces into deterministic function calls and mutations."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,re,urllib.parse
from typing import Any

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),default=str)
def sha(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
@dataclass(frozen=True)
class ResolvedCall:
 index:int
 method:str
 app_name:str
 api_name:str
 arguments_json:str
 parameter_docs_json:str
 def arguments(self):return json.loads(self.arguments_json)
 def parameter_docs(self):return json.loads(self.parameter_docs_json)
@dataclass(frozen=True)
class CallMutation:
 mutation_id:str
 call_index:int
 field_name:str
 mutation_kind:str
 arguments_json:str
 def arguments(self):return json.loads(self.arguments_json)
def _matcher(path):
 names=re.findall(r'\{(\w+)\}',path);pattern=re.escape(path)
 for name in names:pattern=pattern.replace(r'\{'+name+r'\}',f'(?P<{name}>[^/]+)')
 return re.compile('^'+pattern+'$')
def _convert(value,kind):
 value=urllib.parse.unquote(value)
 if 'integer' in kind:return int(value)
 if kind=='number':return float(value)
 if kind=='boolean':return value.lower()=='true'
 return value
class TraceResolver:
 def __init__(self):self.docs={}
 def docs_for(self,app):
  if app not in self.docs:
   from appworld.api_docs import prepare_api_docs
   self.docs[app]=prepare_api_docs(app,include_private_apis=True)
  return self.docs[app]
 def resolve(self,index,call):
  url=str(call['url']).split('?',1)[0];app=url.strip('/').split('/',1)[0]
  for doc in self.docs_for(app):
   if str(doc['method']).lower()!=str(call['method']).lower():continue
   match=_matcher(doc['path']).match(url)
   if not match:continue
   parameter_docs={x['name']:x for x in doc.get('parameters',[])};args=dict(call.get('data') or {});args.update({k:_convert(v,parameter_docs.get(k,{}).get('type','string')) for k,v in match.groupdict().items()});return ResolvedCall(index,str(call['method']).lower(),app,doc['api_name'],canonical(args),canonical(parameter_docs))
  raise LookupError((call.get('method'),url))
 def resolve_all(self,calls):return [self.resolve(i,x) for i,x in enumerate(calls)]
def execute_call(world,call,arguments=None):return world.requester.request(call.app_name,call.api_name,**(call.arguments() if arguments is None else arguments))
def _enum_values(doc):
 values=[]
 for constraint in doc.get('constraints') or []:
  match=re.search(r'value in (\[[^]]*\])',constraint)
  if match:
   try:values.extend(json.loads(match.group(1).replace("'",'"')))
   except Exception:pass
 return values
def mutations_for(call,max_mutations=12):
 args=call.arguments();docs=call.parameter_docs();output=[];sensitive=('token','password','username','email','phone','card','cvv');textual=('name','title','content','description','message','note','query','reason','subject','text')
 for field in sorted(args):
  lower=field.lower();value=args[field];doc=docs.get(field,{})
  if any(x in lower for x in sensitive):continue
  variants=[]
  enums=_enum_values(doc)
  for option in enums:
   if option!=value:variants.append(('enum_alternative',option))
  if isinstance(value,bool):variants.append(('boolean_flip',not value))
  elif isinstance(value,int):
   for candidate in (value+1,value-1,1,2):
    if candidate!=value and candidate>=0:variants.append(('integer_alternative',candidate))
  elif isinstance(value,float):
   for candidate in (value+1.0,max(0.0,value-1.0)):
    if candidate!=value:variants.append(('number_alternative',candidate))
  elif isinstance(value,str) and any(x in lower for x in textual):variants.append(('text_alternative',value+' [alternative]'))
  elif isinstance(value,list) and value:
   variants.append(('list_drop_last',value[:-1]))
   if len(value)>1:variants.append(('list_reverse',list(reversed(value))))
  seen=set()
  for kind,candidate in variants:
   key=canonical(candidate)
   if key in seen:continue
   seen.add(key);mutated=dict(args);mutated[field]=candidate;mid=hashlib.sha256(f'{call.index}|{field}|{kind}|{canonical(candidate)}'.encode()).hexdigest();output.append(CallMutation(mid,call.index,field,kind,canonical(mutated)))
 return sorted(output,key=lambda x:x.mutation_id)[:max_mutations]
def redacted_arguments(arguments):
 output={};sensitive=('token','password','username','email','phone','card','cvv')
 for key,value in arguments.items():output[key]='<REDACTED>' if any(x in key.lower() for x in sensitive) else value
 return output
