"""One-shot locked adaptive SAT recurrent guard confirmation."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any
from analysis.recurrent_parallel_adaptive_guard_sat import _hits
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_sat_core import run_noisy_sat_recurrence
LOCK_SCHEMA='recurrent_parallel_adaptive_guard_sat_execution_lock_v1'; MANIFEST_STATUS='RPD_ADAPTIVE_SAT_MANIFEST_FROZEN'
def _r(p:str|Path)->Path:
 v=Path(p); return v if v.is_absolute() else REPO_ROOT/v
def _h(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_lock(p:Path)->tuple[dict[str,Any],dict[str,bool]]:
 lock=json.loads(p.read_text());
 if lock.get('schema')!=LOCK_SCHEMA or lock.get('status')!='EXECUTION_LOCKED': raise ValueError('invalid adaptive SAT lock')
 checks={k:_h(_r(v['path']))==v['sha256'] for k,v in lock['files'].items()}
 if not all(checks.values()): raise ValueError(checks)
 return lock,checks
def run(a:argparse.Namespace)->dict[str,Any]:
 lp=_r(a.execution_lock); lock,checks=verify_lock(lp); c=json.loads(_r(lock['files']['contract_json']['path']).read_text()); policy=c['policy']; manifest=json.loads(_r(lock['files']['manifest']['path']).read_text());
 if manifest.get('status')!=MANIFEST_STATUS: raise ValueError('manifest not frozen')
 instances=list(manifest['rows']); rows=[]
 for idx,inst in enumerate(instances):
  d=int(inst['partition_diameter'])
  for eta in map(float,policy['eta_fp']):
   for system in c['systems']:
    hits=_hits(eta,d,float(policy['p0'])) if system=='R_adaptive' else None
    rows.append(run_noisy_sat_recurrence(inst,system=system,eta_fp=eta,round_cap=int(policy['round_cap']),noise_seed=int(policy['noise_seed']),confirmation_hits=hits))
  if (idx+1)%10==0: print(json.dumps({'event':'adaptive_sat_confirmation_progress','instances_completed':idx+1}),flush=True)
 counts=Counter((r['partition_diameter'],r['eta_fp'],r['system']) for r in rows); card={'rows':len(rows)==int(c['expected_rows']),'cells':len(counts)==96 and all(v==50 for v in counts.values()),'instances':len({r['instance_id'] for r in rows})==200}
 sem={'same_round':all(r['same_round_cross_agent_reads']==0 for r in rows),'message_age':all(r['messages_delivered']==0 or r['maximum_message_age']==1 for r in rows),'local':all(r['local_candidates_valid'] for r in rows),'official':all(not r['solved'] or r['official_verification'] for r in rows),'planted':all(not r['planted_assignment_used'] for r in rows)}
 ok=all(card.values()) and all(sem.values()); return {'schema':'recurrent_parallel_adaptive_sat_raw_v1','status':'RPD_ADAPTIVE_SAT_RAW_COMPLETE' if ok else 'RPD_ADAPTIVE_SAT_PROTOCOL_FAIL','lock_checks':checks,'input_hashes':{k:v['sha256'] for k,v in lock['files'].items()},'execution_lock_sha256':_h(lp),'cardinality':card,'semantics':sem,'rows':rows,'honesty':{'one_shot':True,'independent_sat_pool':True,'no_gpu_or_llm':True}}
def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--execution-lock',type=Path,default=Path('specs/recurrent_parallel_adaptive_guard_sat_execution_lock_v1.json')); ap.add_argument('--output',type=Path,default=Path('results/recurrent_parallel_adaptive_guard_sat_confirmation/raw_results.json')); a=ap.parse_args(); out=_r(a.output)
 if out.exists(): raise SystemExit('refusing one-shot overwrite')
 p=run(a); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n'); print(json.dumps({'status':p['status'],'rows':len(p['rows']),'sha256':_h(out)}));
 if p['status']!='RPD_ADAPTIVE_SAT_RAW_COMPLETE': raise SystemExit(2)
if __name__=='__main__':main()
