"""Typed, deduplicated, selective provenance for AppWorld candidate verification."""
from __future__ import annotations
import hashlib,json,re
from typing import Any
SENSITIVE=('password','token','card','cvv')
CONTROL_FIELDS={'page_index','page_limit','sort_by','direction','query','min_created_at','max_created_at'}
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),default=str)
def sensitive(key):return any(x in str(key).lower() for x in SENSITIVE)
def aliases(field):
 out={field.lower()}
 if field.lower().endswith('_id'):out.add('id')
 if field.lower().endswith('_email'):out.add('email')
 if field.lower().endswith('_name'):out.add('name')
 return out
def scalar_equal(a,b):
 if isinstance(a,str) and isinstance(b,str):return a.strip().casefold()==b.strip().casefold()
 if isinstance(a,(int,float)) and isinstance(b,(int,float)) and not isinstance(a,bool) and not isinstance(b,bool):return float(a)==float(b)
 return False
def flatten(record,prefix=()):
 output=[]
 if isinstance(record,dict):
  for key,value in record.items():
   if sensitive(key):continue
   if isinstance(value,(dict,list)):output+=flatten(value,prefix+(str(key),))
   elif isinstance(value,(str,int,float)) and not isinstance(value,bool):output.append((prefix+(str(key),),value))
 elif isinstance(record,list):
  for i,value in enumerate(record):output+=flatten(value,prefix+(str(i),))
 return output
def records(value):
 if isinstance(value,list):
  return [x for x in value if isinstance(x,dict)]
 if isinstance(value,dict):
  nested=[x for x in value.values() if isinstance(x,list) and x and all(isinstance(y,dict) for y in x)]
  return [value]+[item for group in nested for item in group]
 return []
def field_matches(field,value,record):return any(path and path[-1].lower() in aliases(field) and scalar_equal(value,observed) for path,observed in flatten(record))
def fingerprint(record):
 ids=[(path[-1],value) for path,value in flatten(record) if path and (path[-1].lower()=='id' or path[-1].lower().endswith('_id'))]
 return hashlib.sha256(canonical(ids if ids else record).encode()).hexdigest()
def candidate_typed_evidence(candidate,other,history,task_goal):
 fields=[k for k in sorted(candidate) if not sensitive(k) and k not in CONTROL_FIELDS];differing=[k for k in fields if candidate.get(k)!=other.get(k)];common=[k for k in fields if candidate.get(k)==other.get(k)];best_by_record={};relations=[]
 for call in history:
  for source in ('response','arguments'):
   for record in records(call[source]):
    changed_matches=[f for f in differing if field_matches(f,candidate.get(f),record)];common_matches=[f for f in common if field_matches(f,candidate.get(f),record)];tier=0;relation='none'
    if differing and len(changed_matches)==len(differing) and common_matches:tier=3;relation='joint_record'
    elif differing and len(changed_matches)==len(differing):tier=1;relation='direct_field'
    if tier:
     key=fingerprint(record);best_by_record[key]=max(tier,best_by_record.get(key,0));relations.append({'tier':tier,'relation':relation,'call_index':call['call_index'],'source':source,'changed_fields':changed_matches,'anchor_fields':common_matches})
 goal_fields=[f for f in differing if isinstance(candidate.get(f),str) and len(candidate[f])>=3 and candidate[f].casefold() in task_goal.casefold()]
 if goal_fields:relations.append({'tier':4,'relation':'task_goal_literal','changed_fields':goal_fields,'anchor_fields':[]})
 max_tier=max([x['tier'] for x in relations],default=0);return {'max_tier':max_tier,'unique_record_count':len(best_by_record),'relation_types':sorted({x['relation'] for x in relations if x['tier']==max_tier}),'relations':relations}
def typed_choice(evidence_a,evidence_b):
 if evidence_a['max_tier']==evidence_b['max_tier']:return None
 return 'A' if evidence_a['max_tier']>evidence_b['max_tier'] else 'B'
