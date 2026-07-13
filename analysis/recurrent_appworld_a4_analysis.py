"""Frozen analysis for AppWorld A4 comparative/provenance development arms."""
from __future__ import annotations
import argparse,json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from analysis.recurrent_appworld_a3_run import H,R
def parse(text):
 try:
  x=json.loads(text)
  if not isinstance(x,dict) or set(x)!={'preferred_candidate','confidence'} or x['preferred_candidate'] not in ('A','B') or type(x['confidence']) not in (int,float) or isinstance(x['confidence'],bool) or not 0<=float(x['confidence'])<=1:return None
  return x['preferred_candidate'],float(x['confidence'])
 except Exception:return None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_comparative_development_v1.json'));ap.add_argument('--manifest',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/prompt_manifest.json'));ap.add_argument('--labels',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/adjudication_manifest.json'));ap.add_argument('--manifest-audit',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/manifest.json'));ap.add_argument('--execution-lock',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/execution_lock.json'));ap.add_argument('--raw',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/raw_model_outputs.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development'));a=ap.parse_args();cp,mp,lp,mapath,lockp,rp=map(R,(a.contract,a.manifest,a.labels,a.manifest_audit,a.execution_lock,a.raw));c=json.loads(cp.read_text());manifest=json.loads(mp.read_text());labels=json.loads(lp.read_text());ma=json.loads(mapath.read_text());lock=json.loads(lockp.read_text());raw=json.loads(rp.read_text());prompts={x['sample_id']:x for x in manifest['rows']};truth={x['sample_id']:x for x in labels['rows']};outputs={x['sample_id']:x for x in raw['rows']};lock_checks={k:H(R(k))==v for k,v in lock['files'].items()};integrity={'raw_complete':raw['status']=='RPD_APPWORLD_A4_RAW_COMPLETE','lock_files':all(lock_checks.values()),'contract_hash':raw['contract_sha256']==H(cp)==lock['contract_sha256'],'manifest_hash':raw['manifest_sha256']==H(mp)==lock['prompt_manifest_sha256'],'execution_lock_hash':raw['execution_lock_sha256']==H(lockp),'model':raw['model']==c['model'],'revision':raw['model_revision']==c['model_revision'],'exact_ids':set(prompts)==set(truth)==set(outputs),'unique_outputs':len(outputs)==len(raw['rows']),'external_pid_survival':raw['generation']['preexisting_pid_survival'] is True,'latency_excluded':raw['generation']['latency_authoritative'] is False};rows=[]
 for sid,p in prompts.items():
  z=parse(outputs[sid]['output_text']);t=truth[sid];rows.append({'sample_id':sid,'pair_id':p['pair_id'],'task_type':p['task_type'],'arm':p['arm'],'order':p['order'],'preferred':t['preferred_candidate'],'parsed':z is not None,'prediction':z[0] if z else None,'confidence':z[1] if z else None,'correct':z is not None and z[0]==t['preferred_candidate']})
 metrics={}
 for arm in c['arms']:
  subset=[x for x in rows if x['arm']==arm];metrics[arm]={'parse_rate':mean(float(x['parsed']) for x in subset),'accuracy':mean(float(x['correct']) for x in subset),'AB_accuracy':mean(float(x['correct']) for x in subset if x['order']=='AB'),'BA_accuracy':mean(float(x['correct']) for x in subset if x['order']=='BA')}
 pair_metrics={}
 for arm in c['arms']:
  groups=defaultdict(list)
  for x in rows:
   if x['arm']==arm:groups[x['pair_id']].append(x)
  pair_metrics[arm]={'order_consistency':mean(float(len(z)==2 and all(x['parsed'] for x in z) and z[0]['prediction']!=z[1]['prediction']) for z in groups.values()),'both_orders_correct':mean(float(len(z)==2 and all(x['correct'] for x in z)) for z in groups.values())}
 det=ma['deterministic_provenance'];d0=all(integrity.values()) and all(ma['checks'].values());d1=pair_metrics['C2_comparative_provenance']['order_consistency']>=.80;d2=metrics['C2_comparative_provenance']['AB_accuracy']>=.70 and metrics['C2_comparative_provenance']['BA_accuracy']>=.70 and pair_metrics['C2_comparative_provenance']['both_orders_correct']>=.60;d3c=metrics['C2_comparative_provenance']['accuracy']-metrics['C1_comparative_local']['accuracy']>=.10;d3d=det['coverage']>=.50 and det['covered_accuracy']>=.80;d4=raw['generation']['latency_authoritative'] is False;gates={'D0_manifest_integrity':d0,'D1_C2_order':d1,'D2_C2_quality':d2,'D3_comparative_value':d3c,'D3_deterministic_value':d3d,'D4_honesty':d4};comparative_go=d0 and d1 and d2 and d3c and d4;deterministic_go=d0 and d3d and d4
 if not d0:status=c['verdicts']['protocol']
 elif comparative_go:status=c['verdicts']['comparative_go']
 elif deterministic_go:status=c['verdicts']['deterministic_go']
 else:status=c['verdicts']['no_go']
 payload={'schema':'recurrent_appworld_a4_analysis_v1','status':status,'routes':{'comparative_go':comparative_go,'deterministic_go':deterministic_go},'gates':gates,'integrity':integrity,'model_metrics':metrics,'pair_metrics':pair_metrics,'deterministic_provenance':{k:v for k,v in det.items() if k!='rows'},'raw_sha256':H(rp),'latency_authoritative':False,'train_only':True,'dev_or_test_used':False,'headline_eligible':False};out=R(a.output_dir);(out/'analysis.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# AppWorld A4 — Comparative Evidence Development','',f"## Verdict: **`{status}`**",'','## Routes','',f"- Comparative LLM GO: **{comparative_go}**",f"- Deterministic provenance GO: **{deterministic_go}**",'','## Model arms','', '| Arm | Accuracy | AB | BA | Order consistency | Both orders correct |','|---|---:|---:|---:|---:|---:|']
 for arm in c['arms']:lines.append(f"| {arm} | {metrics[arm]['accuracy']:.3f} | {metrics[arm]['AB_accuracy']:.3f} | {metrics[arm]['BA_accuracy']:.3f} | {pair_metrics[arm]['order_consistency']:.3f} | {pair_metrics[arm]['both_orders_correct']:.3f} |")
 lines+=['','## Deterministic provenance','',f"- Coverage: {det['coverage']:.3f}",f"- Covered accuracy: {det['covered_accuracy']:.3f}",f"- Overall correct-or-abstain: {det['overall_correct_or_abstain']:.3f}",'','This is exposed train development. A GO only authorizes a frozen untouched-dev confirmation.'];(out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'comparative_go':comparative_go,'deterministic_go':deterministic_go,'report':str((out/'REPORT.md').relative_to(R('.')))}))
if __name__=='__main__':main()
