"""Exposure-calibrated recurrent guard development on the exposed graph pool."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from statistics import mean
from collections import Counter
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import run_noisy_recurrent_correction
from analysis.recurrent_parallel_adaptive_guard_sat import _hits
SCHEMA='recurrent_parallel_adaptive_guard_graph_contract_v1'; FAIL=5000
def _r(p):
 v=Path(p); return v if v.is_absolute() else REPO_ROOT/v
def _h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_adaptive_guard_graph_v1.json')); ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_adaptive_guard_graph')); a=ap.parse_args(); cp=_r(a.contract); c=json.loads(cp.read_text())
 if c.get('schema')!=SCHEMA or c.get('status')!='FROZEN_BEFORE_GRAPH_ADAPTIVE_OUTCOMES': raise ValueError('graph adaptive contract not frozen')
 sat=json.loads(_r(c['sat_gate']).read_text());
 if sat.get('status')!='RPD_ADAPTIVE_GUARD_SAT_CONFIRMATION_PASS': raise ValueError('SAT adaptive prerequisite failed')
 mp=_r(c['graph_manifest']); instances=list(json.loads(mp.read_text())['rows']); controls=list(json.loads(_r(c['graph_controls']).read_text())['rows']); etas=list(map(float,c['eta_fp']))
 rows=[]
 for i,inst in enumerate(instances):
  d=inst['partition_diameter']
  for eta in etas: rows.append(run_noisy_recurrent_correction(inst,system='R_adaptive',eta_fp=eta,round_cap=32,noise_seed=int(c['noise_seed']),confirmation_hits=_hits(eta,d,float(c['p0']))))
  if (i+1)%10==0: print(json.dumps({'event':'adaptive_graph_progress','instances_completed':i+1}),flush=True)
 replay=rows[:8]; idx={x['instance_id']:x for x in instances}; mismatch=sum(int(run_noisy_recurrent_correction(idx[x['instance_id']],system='R_adaptive',eta_fp=x['eta_fp'],round_cap=32,noise_seed=int(c['noise_seed']),confirmation_hits=_hits(x['eta_fp'],x['partition_diameter'],float(c['p0'])))!=x) for x in replay)
 violations=mismatch+sum(int(x['same_round_cross_agent_reads']!=0 or (x['messages_delivered']>0 and x['maximum_message_age']!=1) or not x['local_candidates_valid'] or (x['solved'] and not x['official_verification']) or x['planted_assignment_used'] or x['confirmation_hits']!=_hits(x['eta_fp'],x['partition_diameter'],float(c['p0']))) for x in rows)
 def summarize(items,system):
  out=[]
  for d in (2,4,8,16):
   for e in etas:
    z=[x for x in items if x['partition_diameter']==d and x['eta_fp']==e and x['system']==system]; out.append({'d':d,'e':e,'system':system,'solve':mean(float(x['solved']) for x in z),'work':mean(float(x['aggregate_work'] if x['solved'] else max(x['aggregate_work'],FAIL)) for x in z),'over':mean(float(x['over_corrections']) for x in z),'queries':mean(float(x['detector_queries']) for x in z)})
  return out
 adaptive=summarize(rows,'R_adaptive'); soft=summarize(controls,'R_soft2'); exact=summarize(controls,'R_exact')
 def L(arr,d,e):return next(x for x in arr if x['d']==d and x['e']==e)
 g0=len(replay)>=8 and violations==0
 g1=all(L(adaptive,d,e)['solve']>=.95 for d in (2,4,8,16) for e in etas)
 g2=all(L(adaptive,d,e)['over']<=L(soft,d,e)['over']+1e-12 for d in (2,4,8,16) for e in etas)
 g3=all(L(adaptive,d,0)['solve']==L(exact,d,0)['solve'] and L(adaptive,d,0)['work']==L(exact,d,0)['work'] for d in (2,4,8,16))
 adaptive_high=L(adaptive,16,.2); soft_high=L(soft,16,.2); g4=adaptive_high['solve']-soft_high['solve']>=.05 and adaptive_high['work']<soft_high['work']
 g5=all('work' in x and 'queries' in x for x in adaptive)
 gates={'G0_integrity':g0,'G1_robust_solve':g1,'G2_hazard_control':g2,'G3_perfect_signal':g3,'G4_high_exposure_value':g4,'G5_overhead_reported':g5}
 if not g0:status='RPD_ADAPTIVE_GUARD_GRAPH_PROTOCOL_FAIL'
 elif all(gates.values()):status='RPD_ADAPTIVE_GUARD_GRAPH_DEV_GO_CONFIRMATION'
 elif g0 and g1 and g2 and g3:status='RPD_ADAPTIVE_GUARD_GRAPH_ROBUST_NO_VALUE'
 else:status='RPD_ADAPTIVE_GUARD_GRAPH_NO_GO'
 comp=[]
 for d in (2,4,8,16):
  for e in etas:
   aa=L(adaptive,d,e); ss=L(soft,d,e); comp.append({'diameter':d,'eta':e,'k':_hits(e,d,float(c['p0'])),'adaptive_solve':aa['solve'],'soft_solve':ss['solve'],'adaptive_work':aa['work'],'soft_work':ss['work'],'adaptive_over':aa['over'],'soft_over':ss['over']})
 p={'schema':'recurrent_parallel_adaptive_guard_graph_results_v1','status':status,'headline_eligible':False,'qwen_authorized':False,'independent_confirmation_authorized':status=='RPD_ADAPTIVE_GUARD_GRAPH_DEV_GO_CONFIRMATION','gates':gates,'integrity':{'replay_rows':len(replay),'violations':violations},'comparison':comp,'rows':rows,'contract_sha256':_h(cp),'sat_gate_sha256':_h(_r(c['sat_gate'])),'manifest_sha256':_h(mp),'controls_sha256':_h(_r(c['graph_controls'])),'implementation_sha256':_h(REPO_ROOT/'experiments/recurrent_parallel_core.py'),'honesty':{'exposed_graph_pool':True,'no_gpu_or_llm':True}}
 out=_r(a.output_dir); out.mkdir(parents=True,exist_ok=True); (out/'results.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
 lines=['# Exposure-Calibrated Recurrent Verification — Graph Development','',f"## Verdict: **`{status}`**",'','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','## Eta=.20','', '| Diameter | k | Adaptive solve | Soft2 solve | Adaptive work | Soft2 work |','|---:|---:|---:|---:|---:|---:|']
 for d in (2,4,8,16):
  x=next(r for r in comp if r['diameter']==d and r['eta']==.2); lines.append(f"| {d} | {x['k']} | {x['adaptive_solve']:.3f} | {x['soft_solve']:.3f} | {x['adaptive_work']:.1f} | {x['soft_work']:.1f} |")
 lines+=['','Development only; a GO requires a new zero-overlap graph confirmation before a cross-substrate adaptive-policy claim.']
 (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n'); print(json.dumps({'status':status,'independent_confirmation_authorized':p['independent_confirmation_authorized'],'rows':len(rows),'report':str((out/'SUMMARY.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
