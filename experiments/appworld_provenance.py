"""Candidate-symmetric entity-provenance extraction for AppWorld proposals."""
from __future__ import annotations
import re
from typing import Any
SENSITIVE=('password','token','card','cvv')
def sensitive(key):return any(x in str(key).lower() for x in SENSITIVE)
def compact(value,cfg,depth=0):
 if depth>2:return '<TRUNCATED>'
 if isinstance(value,dict):
  out={}
  for key in sorted(value):
   if sensitive(key):continue
   out[key]=compact(value[key],cfg,depth+1)
   if len(out)>=cfg['max_dict_items']:break
  return out
 if isinstance(value,list):return [compact(x,cfg,depth+1) for x in value[:cfg['max_list_items']]]
 if isinstance(value,str):return value[:cfg['max_string_chars']]
 return value
def scalars(value,path=(),parent=None):
 if isinstance(value,dict):
  for key,item in value.items():
   if sensitive(key):continue
   yield from scalars(item,path+(str(key),),value)
 elif isinstance(value,list):
  for i,item in enumerate(value):yield from scalars(item,path+(str(i),),item if isinstance(item,dict) else parent)
 elif isinstance(value,(str,int,float)) and not isinstance(value,bool):yield path,value,parent
def norm_tokens(name):return [x for x in re.split(r'[^a-z0-9]+',name.lower()) if x]
def compatible(candidate_field,path):
 if not path:return False
 terminal=path[-1].lower();ct=norm_tokens(candidate_field);pt=norm_tokens(terminal)
 if terminal==candidate_field.lower():return True
 if candidate_field.lower().endswith('_id') and terminal=='id':return True
 if candidate_field.lower().endswith('_email') and terminal=='email':return True
 if candidate_field.lower().endswith('_name') and terminal=='name':return True
 return bool(set(ct)&set(pt))
def equal(a,b):
 if isinstance(a,str) and isinstance(b,str):return a.strip().casefold()==b.strip().casefold()
 if isinstance(a,(int,float)) and isinstance(b,(int,float)) and not isinstance(a,bool) and not isinstance(b,bool):return float(a)==float(b)
 return False
def citations(field,value,history,task_goal,cfg,max_citations=3):
 output=[]
 if isinstance(value,str) and len(value)>=3 and value.casefold() in task_goal.casefold():output.append({'source':'task_goal','path':'text','value':compact(value,cfg)})
 for call in history:
  for source in ('response','arguments'):
   for path,observed,parent in scalars(call[source]):
    if not compatible(field,path) or not equal(value,observed):continue
    output.append({'source':source,'call_index':call['call_index'],'app':call['app_name'],'api':call['api_name'],'path':'.'.join(path),'evidence':compact(parent if parent is not None else observed,cfg)})
    if len(output)>=max_citations:return output
 return output
def candidate_evidence(arguments,differing_fields,history,task_goal,cfg,max_citations=3):
 by_field={field:citations(field,arguments.get(field),history,task_goal,cfg,max_citations) for field in differing_fields};return {'support_count':sum(len(x) for x in by_field.values()),'by_field':by_field}
def deterministic_choice(evidence_a,evidence_b):
 a=evidence_a['support_count'];b=evidence_b['support_count']
 if a==b:return None
 return 'A' if a>b else 'B'
