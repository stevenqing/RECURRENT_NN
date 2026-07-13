"""Cost-sensitive recurrent verification development across graph and SAT."""
from __future__ import annotations
import argparse, hashlib, json, math
from collections import Counter
from pathlib import Path
from statistics import mean
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import run_noisy_recurrent_correction
from experiments.recurrent_parallel_sat_core import run_noisy_sat_recurrence
SCHEMA='recurrent_parallel_cost_sensitive_guard_contract_v1'; FAIL=5000
def R(p):
 v=Path(p); return v if v.is_absolute() else REPO_ROOT/v
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def exposure(rows,d):
 z=[r for r in rows if r['partition_diameter']==d and r['eta_fp']==0 and r['system']=='R_exact']; q=mean(r['detector_queries'] for r in z); dead=mean(r['true_correction_exposures'] for r in z); return {'live':q-dead,'dead':dead}
def objective(k,eta,live,dead):
 if eta==0:return live+dead
 eq=(1-eta**k)/(1-eta); return live*eq+dead*k+FAIL*(1-(1-eta**k)**live)
def choose(eta,x,ks):
 vals=[(objective(k,eta,x['live'],x['dead']),k) for k in ks]; best=min(v for v,_ in vals); return min(k for v,k in vals if abs(v-best)<1e-12)
def summarize(rows,substrate):
 out=[]
 for d,e in sorted({(r['partition_diameter'],r['eta_fp']) for r in rows}):
  z=[r for r in rows if r['partition_diameter']==d and r['eta_fp']==e]; out.append({'substrate':substrate,'diameter':d,'eta':e,'k':z[0]['confirmation_hits'],'solve':mean(float(r['solved']) for r in z),'work':mean(float(r['aggregate_work'] if r['solved'] else max(r['aggregate_work'],FAIL)) for r in z),'over':mean(float(r['over_corrections']) for r in z),'queries':mean(float(r['detector_queries']) for r in z)})
 return out
def L(arr,d,e):return next(x for x in arr if x['diameter']==d and x['eta']==e)
def control(rows,d,e,system):
 z=[r for r in rows if r['partition_diameter']==d and r['eta_fp']==e and r['system']==system]; return {'solve':mean(float(r['solved']) for r in z),'work':mean(float(r['aggregate_work'] if r['solved'] else max(r['aggregate_work'],FAIL)) for r in z),'over':mean(float(r['over_corrections']) for r in z)}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_cost_sensitive_guard_v1.json')); ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_cost_sensitive_guard')); a=ap.parse_args(); cp=R(a.contract); c=json.loads(cp.read_text())
 if c.get('schema')!=SCHEMA or c.get('status')!='FROZEN_BEFORE_COST_OUTCOMES':raise ValueError('cost contract not frozen')
 gcal=json.loads(R(c['graph_calibration']).read_text())['rows']; scal=json.loads(R(c['sat_calibration']).read_text())['rows']; gm=list(json.loads(R(c['graph_manifest']).read_text())['rows']); sm=list(json.loads(R(c['sat_manifest']).read_text())['rows']); etas=list(map(float,c['eta_fp'])); ks=list(map(int,c['k_candidates']))
 exposures={'graph':{d:exposure(gcal,d) for d in (2,4,8,16)},'sat':{d:exposure(scal,d) for d in (2,4,8,16)}}; schedule={sub:{d:{e:choose(e,x[d],ks) for e in etas} for d in (2,4,8,16)} for sub,x in exposures.items()}
 grows=[]; srows=[]
 for i,inst in enumerate(gm):
  d=inst['partition_diameter']
  for e in etas:grows.append(run_noisy_recurrent_correction(inst,system='R_adaptive',eta_fp=e,round_cap=32,noise_seed=int(c['noise_seed']),confirmation_hits=schedule['graph'][d][e]))
  if (i+1)%25==0:print(json.dumps({'event':'cost_guard_graph','completed':i+1}),flush=True)
 for i,inst in enumerate(sm):
  d=inst['partition_diameter']
  for e in etas:srows.append(run_noisy_sat_recurrence(inst,system='R_adaptive',eta_fp=e,round_cap=32,noise_seed=int(c['noise_seed']),confirmation_hits=schedule['sat'][d][e]))
  if (i+1)%25==0:print(json.dumps({'event':'cost_guard_sat','completed':i+1}),flush=True)
 replay=grows[:4]+srows[:4]; gi={x['instance_id']:x for x in gm}; si={x['instance_id']:x for x in sm}; mismatch=0
 for x in replay:
  d=x['partition_diameter']; k=schedule['graph' if x['instance_id'] in gi else 'sat'][d][x['eta_fp']]; rr=run_noisy_recurrent_correction(gi[x['instance_id']],system='R_adaptive',eta_fp=x['eta_fp'],round_cap=32,noise_seed=int(c['noise_seed']),confirmation_hits=k) if x['instance_id'] in gi else run_noisy_sat_recurrence(si[x['instance_id']],system='R_adaptive',eta_fp=x['eta_fp'],round_cap=32,noise_seed=int(c['noise_seed']),confirmation_hits=k); mismatch+=int(rr!=x)
 allrows=grows+srows; violations=mismatch+sum(int(r['same_round_cross_agent_reads']!=0 or (r['messages_delivered']>0 and r['maximum_message_age']!=1) or not r['local_candidates_valid'] or (r['solved'] and not r['official_verification']) or r['planted_assignment_used']) for r in allrows)
 gs=summarize(grows,'graph'); ss=summarize(srows,'sat'); gsoft=json.loads(R(c['graph_calibration']).read_text())['rows']; ssoft=json.loads(R(c['sat_calibration']).read_text())['rows']
 k0=violations==0 and len(replay)>=8
 k1=all(x['solve']>=.95 for x in gs+ss)
 ga=L(gs,16,.2); gc=control(gsoft,16,.2,'R_soft2'); k2=ga['solve']>=.95 and ga['work']<gc['work'] and ga['over']<=gc['over']
 k3=all(L(ss,d,.2)['solve']>=.95 and L(ss,d,.2)['work']<control(ssoft,d,.2,'R_soft2')['work'] for d in (8,16))
 k4=all(x['k']<8 and (x['eta']>.1 or x['k']<=5) and 'queries' in x for x in gs+ss)
 k5=True
 for sub,arr,ctrl in [('graph',gs,gsoft),('sat',ss,ssoft)]:
  for d in (2,4,8,16):
   a0=L(arr,d,0); e0=control(ctrl,d,0,'R_exact'); k5=k5 and a0['solve']==e0['solve'] and a0['work']==e0['work']
 k6=all(x['k']==choose(x['eta'],exposures[x['substrate']][x['diameter']],ks) for x in gs+ss)
 gates={'K0_integrity':k0,'K1_robust_solve':k1,'K2_graph_high_exposure_value':k2,'K3_sat_high_exposure_value':k3,'K4_verification_economy':k4,'K5_perfect_signal':k5,'K6_objective_argmin':k6}
 if not k0:status='RPD_COST_SENSITIVE_GUARD_PROTOCOL_FAIL'
 elif all(gates.values()):status='RPD_COST_SENSITIVE_GUARD_DEV_GO_CONFIRMATION'
 elif k0 and k1 and k5 and k6:status='RPD_COST_SENSITIVE_GUARD_ROBUST_NO_VALUE'
 else:status='RPD_COST_SENSITIVE_GUARD_NO_GO'
 p={'schema':'recurrent_parallel_cost_sensitive_guard_results_v1','status':status,'headline_eligible':False,'qwen_authorized':False,'independent_confirmation_authorized':status=='RPD_COST_SENSITIVE_GUARD_DEV_GO_CONFIRMATION','gates':gates,'exposures':exposures,'schedule':schedule,'graph_summary':gs,'sat_summary':ss,'rows':allrows,'integrity':{'replay_rows':len(replay),'violations':violations},'contract_sha256':H(cp),'implementation_graph_sha256':H(REPO_ROOT/'experiments/recurrent_parallel_core.py'),'implementation_sat_sha256':H(REPO_ROOT/'experiments/recurrent_parallel_sat_core.py'),'honesty':{'exposure_calibration_and_evaluation_same_exposed_pools':True,'no_gpu_or_llm':True}}
 out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);(out/'results.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
 lines=['# Cost-Sensitive Recurrent Verification Development','',f"## Verdict: **`{status}`**",'','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','## Frozen schedules','']
 for sub in ('graph','sat'):
  lines+=['',f"### {sub}",'','| Delta | .01 | .02 | .05 | .10 | .20 |','|---:|---:|---:|---:|---:|---:|']
  for d in (2,4,8,16):lines.append(f"| {d} | "+' | '.join(str(schedule[sub][d][e]) for e in (.01,.02,.05,.1,.2))+' |')
 lines+=['','Development uses exposed calibration/evaluation pools. A GO requires new zero-overlap graph and SAT confirmations.']
 (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n'); print(json.dumps({'status':status,'independent_confirmation_authorized':p['independent_confirmation_authorized'],'rows':len(allrows),'report':str((out/'SUMMARY.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
