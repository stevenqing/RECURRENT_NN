"""One-shot joint cost-sensitive recurrent confirmation runner."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import run_noisy_recurrent_correction
from experiments.recurrent_parallel_sat_core import run_noisy_sat_recurrence
LOCK='recurrent_parallel_cost_sensitive_execution_lock_v1'; STATUS='RPD_COST_SENSITIVE_MANIFESTS_FROZEN'
def R(p):
 v=Path(p);return v if v.is_absolute() else REPO_ROOT/v
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_lock(p):
 l=json.loads(p.read_text());
 if l.get('schema')!=LOCK or l.get('status')!='EXECUTION_LOCKED':raise ValueError('bad lock')
 c={k:H(R(v['path']))==v['sha256'] for k,v in l['files'].items()}
 if not all(c.values()):raise ValueError(c)
 return l,c
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execution-lock',type=Path,default=Path('specs/recurrent_parallel_cost_sensitive_execution_lock_v1.json'));ap.add_argument('--output',type=Path,default=Path('results/recurrent_parallel_cost_sensitive_confirmation/raw_results.json'));a=ap.parse_args();out=R(a.output)
 if out.exists():raise SystemExit('refusing overwrite')
 lp=R(a.execution_lock);lock,checks=verify_lock(lp);c=json.loads(R(lock['files']['contract_json']['path']).read_text());gm=list(json.loads(R(lock['files']['graph_manifest']['path']).read_text())['rows']);sm=list(json.loads(R(lock['files']['sat_manifest']['path']).read_text())['rows']);rows=[]
 for sub,instances,fn in [('graph',gm,run_noisy_recurrent_correction),('sat',sm,run_noisy_sat_recurrence)]:
  for i,inst in enumerate(instances):
   d=str(inst['partition_diameter'])
   for e in c['eta_fp']:
    for system in c['systems']:
     k=c['schedule'][sub][d][str(float(e))] if system=='R_adaptive' else None; r=fn(inst,system=system,eta_fp=e,round_cap=c['round_cap'],noise_seed=c['noise_seed'],confirmation_hits=k);r['substrate']=sub;rows.append(r)
   if (i+1)%25==0:print(json.dumps({'event':'cost_confirmation','substrate':sub,'completed':i+1}),flush=True)
 counts=Counter((r['substrate'],r['partition_diameter'],r['eta_fp'],r['system']) for r in rows);card={'rows':len(rows)==c['expected_rows'],'cells':len(counts)==192 and all(v==50 for v in counts.values()),'instances':len({(r['substrate'],r['instance_id']) for r in rows})==400};sem={'same_round':all(r['same_round_cross_agent_reads']==0 for r in rows),'age':all(r['messages_delivered']==0 or r['maximum_message_age']==1 for r in rows),'local':all(r['local_candidates_valid'] for r in rows),'official':all(not r['solved'] or r['official_verification'] for r in rows),'planted':all(not r['planted_assignment_used'] for r in rows)};ok=all(card.values()) and all(sem.values());p={'schema':'cost_sensitive_joint_raw_v1','status':'RPD_COST_SENSITIVE_RAW_COMPLETE' if ok else 'RPD_COST_SENSITIVE_PROTOCOL_FAIL','lock_checks':checks,'input_hashes':{k:v['sha256'] for k,v in lock['files'].items()},'cardinality':card,'semantics':sem,'rows':rows,'honesty':{'one_shot':True,'new_graph_and_sat_pools':True,'no_gpu_or_llm':True}};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(p,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':p['status'],'rows':len(rows),'sha256':H(out)}))
 if not ok:raise SystemExit(2)
if __name__=='__main__':main()
