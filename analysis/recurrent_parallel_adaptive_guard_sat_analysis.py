"""Frozen analysis for independent adaptive SAT recurrent guard confirmation."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any
from analysis.recurrent_parallel_adaptive_guard_sat import _hits
from analysis.recurrent_parallel_adaptive_guard_sat_run import verify_lock
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_parallel_sat_core import run_noisy_sat_recurrence
FAIL=5000
def _r(p:str|Path)->Path:
 v=Path(p); return v if v.is_absolute() else REPO_ROOT/v
def _h(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def _summ(rows:list[dict[str,Any]])->list[dict[str,Any]]:
 out=[]
 for d,e,s in sorted({(r['partition_diameter'],r['eta_fp'],r['system']) for r in rows}):
  x=[r for r in rows if r['partition_diameter']==d and r['eta_fp']==e and r['system']==s]; out.append({'diameter':d,'eta':e,'system':s,'solve':mean(float(r['solved']) for r in x),'work':mean(float(r['aggregate_work'] if r['solved'] else max(r['aggregate_work'],FAIL)) for r in x),'over':mean(float(r['over_corrections']) for r in x),'queries':mean(float(r['detector_queries']) for r in x),'n':len(x)})
 return out
def _l(s:list[dict[str,Any]],d:int,e:float,sys:str)->dict[str,Any]:return next(r for r in s if r['diameter']==d and r['eta']==e and r['system']==sys)
def _render(p:dict[str,Any])->str:
 lines=['# Adaptive SAT Recurrent Guard Independent Confirmation','',f"## Verdict: **`{p['status']}`**",'', '- Independent SAT instances: 200 (50/diameter)','- Adaptive, exact, soft2, commit; six eta values; 4,800 rows','- GPU/LLM use: none','','## Frozen gates','', '| Gate | Result |','|---|---:|']+[f"| `{k}` | **{'PASS' if v else 'FAIL'}** |" for k,v in p['gates'].items()]+['','## Eta=.20 repair','', '| Diameter | k | Adaptive solve | Soft2 solve | Adaptive work | Soft2 work | Adaptive over | Soft2 over |','|---:|---:|---:|---:|---:|---:|---:|---:|']
 for r in p['eta20']:lines.append(f"| {r['diameter']} | {r['k']} | {r['adaptive_solve']:.3f} | {r['soft_solve']:.3f} | {r['adaptive_work']:.1f} | {r['soft_work']:.1f} | {r['adaptive_over']:.2f} | {r['soft_over']:.2f} |")
 lines+=['','## Integrity','',f"- Lock checks: `{sum(p['lock_checks'].values())}/{len(p['lock_checks'])}`.",f"- Replay rows/mismatches: `{p['integrity']['replay_rows']}/{p['integrity']['replay_mismatches']}`.",f"- Schedule/control/protocol violations: `{p['integrity']['violations']}`.",'','## Claim boundary','', 'A pass independently confirms exposure-calibrated recurrent verification on the synthetic long-diameter SAT substrate. The graph study used fixed two-hit, so a single cross-substrate adaptive-policy claim still requires applying the same formula to graph or carefully scoping the policies.','', '## Artifacts','', '- [Raw results](raw_results.json)','- [Analysis JSON](analysis.json)','- [Frozen manifest](../recurrent_parallel_adaptive_guard_sat_manifest/GENERATION.md)','- [Confirmation contract](../../specs/recurrent_parallel_adaptive_guard_sat_confirmation_v1.md)','']
 return '\n'.join(lines)
def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--raw',type=Path,default=Path('results/recurrent_parallel_adaptive_guard_sat_confirmation/raw_results.json')); ap.add_argument('--execution-lock',type=Path,default=Path('specs/recurrent_parallel_adaptive_guard_sat_execution_lock_v1.json')); ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_adaptive_guard_sat_confirmation')); a=ap.parse_args(); rp=_r(a.raw); lp=_r(a.execution_lock); lock,checks=verify_lock(lp); raw=json.loads(rp.read_text()); c=json.loads(_r(lock['files']['contract_json']['path']).read_text()); rows=list(raw['rows']); summary=_summ(rows); manifest=list(json.loads(_r(lock['files']['manifest']['path']).read_text())['rows']); idx={r['instance_id']:r for r in manifest}
 replay=[r for r in rows if r['system']=='R_adaptive' and r['eta_fp']==.2][:8]; mismatch=0
 for expected in replay:
  d=expected['partition_diameter']; rr=run_noisy_sat_recurrence(idx[expected['instance_id']],system='R_adaptive',eta_fp=.2,round_cap=32,noise_seed=20260712,confirmation_hits=_hits(.2,d,.95)); mismatch+=int(rr!=expected)
 violations=mismatch+sum(int(r['same_round_cross_agent_reads']!=0 or (r['messages_delivered']>0 and r['maximum_message_age']!=1) or not r['local_candidates_valid'] or (r['solved'] and not r['official_verification']) or r['planted_assignment_used']) for r in rows)
 for d in (2,4,8,16):
  for e in (0,.01,.02,.05,.1,.2):
     expected=_hits(e,d,.95); violations+=sum(int(r['confirmation_hits']!=expected) for r in rows if r['partition_diameter']==d and r['eta_fp']==e and r['system']=='R_adaptive')
 integrity={'replay_rows':len(replay),'replay_mismatches':mismatch,'violations':violations}
 c0=raw['status']=='RPD_ADAPTIVE_SAT_RAW_COMPLETE' and all(raw['cardinality'].values()) and all(raw['semantics'].values()) and all(checks.values()) and len(replay)>=8 and violations==0
 c1=all(_l(summary,d,0,'R_adaptive')['solve']>=.95 and _l(summary,d,0,'R_adaptive')['solve']==_l(summary,d,0,'R_exact')['solve'] and _l(summary,d,0,'R_adaptive')['work']==_l(summary,d,0,'R_exact')['work'] for d in (2,4,8,16))
 c2=all(_l(summary,d,e,'R_adaptive')['solve']>=.95 for d in (2,4,8,16) for e in (0,.01,.02,.05,.1,.2))
 c3=_l(summary,8,.2,'R_adaptive')['solve']-_l(summary,8,.2,'R_soft2')['solve']>=.05 and _l(summary,16,.2,'R_adaptive')['solve']-_l(summary,16,.2,'R_soft2')['solve']>=.5
 c4=all(_l(summary,d,e,'R_adaptive')['over']<=_l(summary,d,e,'R_soft2')['over']+1e-12 for d in (2,4,8,16) for e in (0,.01,.02,.05,.1,.2)) and _l(summary,16,.2,'R_adaptive')['over']<=1
 c5=all(_l(summary,d,.2,'R_adaptive')['solve']>_l(summary,d,.2,'R_soft2')['solve'] and _l(summary,d,.2,'R_adaptive')['work']<_l(summary,d,.2,'R_soft2')['work'] for d in (8,16))
 exact_over=[mean(_l(summary,d,e,'R_exact')['over'] for d in (2,4,8,16)) for e in (0,.01,.02,.05,.1,.2)]; c6=all(_l(summary,d,0,'R_adaptive')['solve']-_l(summary,d,0,'R_commit')['solve']>=.8 for d in (2,4,8,16)) and exact_over[-1]>exact_over[0]
 gates={'C0_integrity':c0,'C1_perfect_signal':c1,'C2_adaptive_robustness':c2,'C3_failed_cell_repair':c3,'C4_hazard_control':c4,'C5_charged_value':c5,'C6_signal_necessity':c6}
 if not c0:status='RPD_ADAPTIVE_GUARD_SAT_PROTOCOL_FAIL'
 elif all(gates.values()):status='RPD_ADAPTIVE_GUARD_SAT_CONFIRMATION_PASS'
 elif c0 and c1 and c2:status='RPD_ADAPTIVE_GUARD_SAT_ROBUST_NO_VALUE'
 else:status='RPD_ADAPTIVE_GUARD_SAT_CONFIRMATION_FAIL'
 eta20=[]
 for d in (2,4,8,16):
  aa=_l(summary,d,.2,'R_adaptive'); ss=_l(summary,d,.2,'R_soft2'); eta20.append({'diameter':d,'k':_hits(.2,d,.95),'adaptive_solve':aa['solve'],'soft_solve':ss['solve'],'adaptive_work':aa['work'],'soft_work':ss['work'],'adaptive_over':aa['over'],'soft_over':ss['over']})
 p={'schema':'recurrent_parallel_adaptive_guard_sat_analysis_v1','status':status,'headline_eligible':False,'qwen_authorized':False,'cross_substrate_adaptive_claim':False,'lock_checks':checks,'raw_sha256':_h(rp),'lock_sha256':_h(lp),'integrity':integrity,'gates':gates,'eta20':eta20,'summary':summary,'honesty':{'independent_sat_pool':True,'graph_adaptive_formula_missing':True,'no_gpu_or_llm':True}}
 out=_r(a.output_dir); out.mkdir(parents=True,exist_ok=True); (out/'analysis.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n'); (out/'RESULTS.md').write_text(_render(p)); print(json.dumps({'status':status,'report':str((out/'RESULTS.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
