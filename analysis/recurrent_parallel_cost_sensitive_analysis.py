"""Frozen analysis for joint graph/SAT cost-sensitive recurrent confirmation."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
from statistics import mean
from analysis.recurrent_parallel_cost_sensitive_run import verify_lock
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_core import run_noisy_recurrent_correction
from experiments.recurrent_parallel_sat_core import run_noisy_sat_recurrence
FAIL=5000
def R(p):
 v=Path(p);return v if v.is_absolute() else REPO_ROOT/v
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def objective(k,e,x):
 if e==0:return x['live']+x['dead']
 return x['live']*(1-e**k)/(1-e)+x['dead']*k+FAIL*(1-(1-e**k)**x['live'])
def choose(e,x):
 vals=[(objective(k,e,x),k) for k in range(1,9)];b=min(v for v,_ in vals);return min(k for v,k in vals if abs(v-b)<1e-12)
def summary(rows):
 out=[]
 for sub,d,e,sys in sorted({(r['substrate'],r['partition_diameter'],r['eta_fp'],r['system']) for r in rows}):
  z=[r for r in rows if r['substrate']==sub and r['partition_diameter']==d and r['eta_fp']==e and r['system']==sys];out.append({'sub':sub,'d':d,'e':e,'sys':sys,'solve':mean(float(r['solved']) for r in z),'work':mean(float(r['aggregate_work'] if r['solved'] else max(r['aggregate_work'],FAIL)) for r in z),'over':mean(float(r['over_corrections']) for r in z),'queries':mean(float(r['detector_queries']) for r in z)})
 return out
def L(s,sub,d,e,sys):return next(x for x in s if x['sub']==sub and x['d']==d and x['e']==e and x['sys']==sys)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--raw',type=Path,default=Path('results/recurrent_parallel_cost_sensitive_confirmation/raw_results.json'));ap.add_argument('--execution-lock',type=Path,default=Path('specs/recurrent_parallel_cost_sensitive_execution_lock_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_cost_sensitive_confirmation'));a=ap.parse_args();rp=R(a.raw);lp=R(a.execution_lock);lock,checks=verify_lock(lp);c=json.loads(R(lock['files']['contract_json']['path']).read_text());raw=json.loads(rp.read_text());rows=raw['rows'];s=summary(rows);gm={r['instance_id']:r for r in json.loads(R(lock['files']['graph_manifest']['path']).read_text())['rows']};sm={r['instance_id']:r for r in json.loads(R(lock['files']['sat_manifest']['path']).read_text())['rows']}
 replay=[r for r in rows if r['system']=='R_adaptive'][:16];m=0
 for x in replay:
  fn=run_noisy_recurrent_correction if x['substrate']=='graph' else run_noisy_sat_recurrence;inst=(gm if x['substrate']=='graph' else sm)[x['instance_id']];k=c['schedule'][x['substrate']][str(x['partition_diameter'])][str(float(x['eta_fp']))];m+=int(fn(inst,system='R_adaptive',eta_fp=x['eta_fp'],round_cap=32,noise_seed=c['noise_seed'],confirmation_hits=k)!=x)
 vio=m+sum(int(r['same_round_cross_agent_reads']!=0 or (r['messages_delivered']>0 and r['maximum_message_age']!=1) or not r['local_candidates_valid'] or (r['solved'] and not r['official_verification']) or r['planted_assignment_used']) for r in rows)
 j0=raw['status']=='RPD_COST_SENSITIVE_RAW_COMPLETE' and all(raw['cardinality'].values()) and all(raw['semantics'].values()) and all(checks.values()) and len(replay)>=16 and vio==0
 j1=all(L(s,sub,d,e,'R_adaptive')['solve']>=.95 for sub in ('graph','sat') for d in (2,4,8,16) for e in c['eta_fp'])
 j2=all(L(s,sub,d,0,'R_adaptive')['solve']==L(s,sub,d,0,'R_exact')['solve'] and L(s,sub,d,0,'R_adaptive')['work']==L(s,sub,d,0,'R_exact')['work'] for sub in ('graph','sat') for d in (2,4,8,16))
 ga=L(s,'graph',16,.2,'R_adaptive');gs=L(s,'graph',16,.2,'R_soft2');j3=ga['solve']>gs['solve'] and ga['work']<gs['work']
 j4=all(L(s,'sat',d,.2,'R_adaptive')['solve']>L(s,'sat',d,.2,'R_soft2')['solve'] and L(s,'sat',d,.2,'R_adaptive')['work']<L(s,'sat',d,.2,'R_soft2')['work'] for d in (8,16))
 j5=all(L(s,sub,d,e,'R_adaptive')['over']<=1 for sub in ('graph','sat') for d in (2,4,8,16) for e in c['eta_fp']) and all(c['schedule'][sub][str(d)][str(float(e))]==choose(e,c['exposures'][sub][str(d)]) for sub in ('graph','sat') for d in (2,4,8,16) for e in c['eta_fp'])
 j6=True
 for sub in ('graph','sat'):
  exact=[mean(L(s,sub,d,e,'R_exact')['over'] for d in (2,4,8,16)) for e in c['eta_fp']];j6=j6 and exact[-1]>exact[0] and all(L(s,sub,d,0,'R_adaptive')['solve']-L(s,sub,d,0,'R_commit')['solve']>=.8 for d in (2,4,8,16))
 gates={'J0_integrity':j0,'J1_adaptive_robustness':j1,'J2_perfect_signal':j2,'J3_graph_high_exposure_value':j3,'J4_sat_high_exposure_value':j4,'J5_hazard_schedule':j5,'J6_signal_necessity':j6}
 if not j0:status='RPD_COST_SENSITIVE_PROTOCOL_FAIL'
 elif all(gates.values()):status='RPD_COST_SENSITIVE_CROSS_SUBSTRATE_CONFIRMATION_PASS'
 elif j0 and j1 and j2:status='RPD_COST_SENSITIVE_ROBUST_SCOPE_LIMITED'
 else:status='RPD_COST_SENSITIVE_CONFIRMATION_FAIL'
 high=[]
 for sub in ('graph','sat'):
  for d in (8,16):
   aa=L(s,sub,d,.2,'R_adaptive');ss=L(s,sub,d,.2,'R_soft2');high.append({'substrate':sub,'diameter':d,'k':c['schedule'][sub][str(d)]['0.2'],'adaptive_solve':aa['solve'],'soft_solve':ss['solve'],'adaptive_work':aa['work'],'soft_work':ss['work'],'adaptive_over':aa['over']})
 p={'schema':'cost_sensitive_joint_analysis_v1','status':status,'headline_eligible':False,'qwen_authorized':False,'lock_checks':checks,'integrity':{'replay_rows':len(replay),'violations':vio},'gates':gates,'high_exposure':high,'summary':s,'raw_sha256':H(rp),'lock_sha256':H(lp),'honesty':{'new_graph_and_sat_pools':True,'calibration_frozen_from_prior_pools':True,'no_gpu_or_llm':True,'real_anchor_missing':True}}
 out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);(out/'analysis.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
 lines=['# Cost-Sensitive Recurrent Verification — Joint Confirmation','',f"## Verdict: **`{status}`**",'','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','## Eta=.20 high exposure','', '| Substrate | Delta | k | Adaptive solve | Soft2 solve | Adaptive work | Soft2 work |','|---|---:|---:|---:|---:|---:|---:|']
 for x in high:lines.append(f"| {x['substrate']} | {x['diameter']} | {x['k']} | {x['adaptive_solve']:.3f} | {x['soft_solve']:.3f} | {x['adaptive_work']:.1f} | {x['soft_work']:.1f} |")
 lines+=['','A pass confirms one cost-sensitive allocation rule across independent graph and SAT pools, with substrate-specific schedules determined only by frozen eta=0 exposure calibration. Real signal and GPU claims remain absent.'];(out/'RESULTS.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'report':str((out/'RESULTS.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
