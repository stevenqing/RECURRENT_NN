"""Frozen scoring for the paired AppWorld A3 semantic write-signal anchor."""
from __future__ import annotations
import argparse,json,math,random
from pathlib import Path
from statistics import mean
from analysis.recurrent_appworld_a3_run import H,R,verify_lock
REPO_ROOT=Path(__file__).resolve().parents[1]
def parse(text):
 try:
  x=json.loads(text)
  if not isinstance(x,dict) or set(x)!={'needs_correction','confidence'} or type(x['needs_correction']) is not bool or type(x['confidence']) not in (int,float) or isinstance(x['confidence'],bool) or not math.isfinite(float(x['confidence'])) or not 0<=float(x['confidence'])<=1:return None
  return x['needs_correction'],float(x['confidence'])
 except Exception:return None
def metrics(rows):
 live=[x for x in rows if not x['label']];dead=[x for x in rows if x['label']];fp=sum(not x['parsed'] or x['prediction'] for x in live)/len(live);fn=sum(not x['parsed'] or not x['prediction'] for x in dead)/len(dead);valid=[x for x in rows if x['parsed']];prob=[x['confidence'] if x['prediction'] else 1-x['confidence'] for x in valid];brier=(sum((p-float(x['label']))**2 for p,x in zip(prob,valid))+len(rows)-len(valid))/len(rows);ece=0.0
 for lo,hi in zip((0,.2,.4,.6,.8),(.2,.4,.6,.8,1.0)):
  z=[(p,x) for p,x in zip(prob,valid) if lo<=p<(hi if hi<1 else hi+1e-12)]
  if z:ece+=len(z)/len(valid)*abs(mean(p for p,_ in z)-mean(float(x['label']) for _,x in z))
 return {'n':len(rows),'valid':len(valid),'parse_rate':len(valid)/len(rows),'eta_fp':fp,'eta_fn':fn,'balanced_accuracy':1-(fp+fn)/2,'brier_fail_closed':brier,'ece_5bin_valid':ece}
def cluster_ci(rows,repetitions=10000):
 groups={k:[x for x in rows if x['task_type']==k] for k in sorted({x['task_type'] for x in rows})};keys=list(groups);rng=random.Random(20260712);values=[]
 for _ in range(repetitions):
  sample=[]
  for key in rng.choices(keys,k=len(keys)):sample+=groups[key]
  values.append(metrics(sample)['balanced_accuracy'])
 values.sort();return [values[int(.025*repetitions)],values[min(repetitions-1,int(.975*repetitions))]]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_signal_anchor_v1.json'));ap.add_argument('--manifest',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/prompt_manifest.json'));ap.add_argument('--labels',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/adjudication_manifest.json'));ap.add_argument('--execution-lock',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/execution_lock.json'));ap.add_argument('--raw',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/raw_model_outputs.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor'));a=ap.parse_args();cp,mp,lp,ep,rp=map(R,(a.contract,a.manifest,a.labels,a.execution_lock,a.raw));c=json.loads(cp.read_text());manifest=json.loads(mp.read_text());labels=json.loads(lp.read_text());raw=json.loads(rp.read_text());_,lock_checks=verify_lock(ep);prompts={x['sample_id']:x for x in manifest['rows']};truth={x['sample_id']:x for x in labels['rows']};outputs={x['sample_id']:x for x in raw['rows']};integrity={'raw_complete':raw.get('status')=='RPD_APPWORLD_A3_RAW_COMPLETE','model':raw.get('model')==c['model'],'revision':raw.get('model_revision')==c['model_revision'],'contract_hash':raw.get('contract_sha256')==H(cp),'manifest_hash':raw.get('manifest_sha256')==H(mp),'execution_lock_hash':raw.get('execution_lock_sha256')==H(ep),'execution_lock_files':all(lock_checks.values()),'exact_ids':set(prompts)==set(truth)==set(outputs),'unique_outputs':len(outputs)==len(raw['rows']),'prompt_hashes':all(outputs[x]['prompt_sha256']==prompts[x]['prompt_sha256'] for x in set(outputs)&set(prompts))};rows=[]
 for sid,p in prompts.items():
  z=parse(outputs.get(sid,{}).get('output_text',''));t=truth[sid];rows.append({'sample_id':sid,'pair_id':p['pair_id'],'task_type':p['task_type'],'label':t['label'],'parsed':z is not None,'prediction':z[0] if z else None,'confidence':z[1] if z else None})
 pooled=metrics(rows);type_metrics={k:metrics([x for x in rows if x['task_type']==k]) for k in sorted({x['task_type'] for x in rows})};pairs=[]
 for pair_id in sorted({x['pair_id'] for x in rows}):
  z=[x for x in rows if x['pair_id']==pair_id];pairs.append({'pair_id':pair_id,'task_type':z[0]['task_type'],'both_correct':all(x['parsed'] and x['prediction']==x['label'] for x in z),'ordered':all(x['parsed'] for x in z) and next(x['confidence'] if x['prediction'] else 1-x['confidence'] for x in z if x['label'])>next(x['confidence'] if x['prediction'] else 1-x['confidence'] for x in z if not x['label'])})
 pair_both=mean(float(x['both_correct']) for x in pairs);pair_ordered=mean(float(x['ordered']) for x in pairs);ci=cluster_ci(rows);s0=all(integrity.values());s1=len(rows)==30 and len(pairs)==15;s2=all(set(x)=={'sample_id','pair_id','task_type','label','parsed','prediction','confidence'} for x in rows);s3=pooled['parse_rate']>=.95;s4=pooled['balanced_accuracy']>=.70 and pooled['eta_fp']<.40 and pooled['eta_fn']<.40;s5=len(type_metrics)==7;gates={'S0_integrity':s0,'S1_pairs':s1,'S2_visibility':s2,'S3_parse':s3,'S4_signal_quality':s4,'S5_clustered_scope':s5}
 if not s0 or not s1 or not s2:status=c['verdicts']['protocol']
 elif all(gates.values()):status=c['verdicts']['pass']
 else:status=c['verdicts']['model_fail']
 batches={x['batch_start']:x for x in raw['rows']};cost={'prompt_tokens':sum(x['prompt_tokens'] for x in raw['rows']),'output_tokens':sum(x['output_tokens'] for x in raw['rows']),'total_generation_seconds':sum(x['batch_latency_seconds'] for x in batches.values()),'mean_amortized_latency_seconds':mean(x['amortized_latency_seconds'] for x in raw['rows'])};payload={'schema':'recurrent_appworld_a3_analysis_v1','status':status,'gates':gates,'integrity':integrity,'pooled':pooled,'task_type_metrics':type_metrics,'cluster_bootstrap_balanced_accuracy_ci95':ci,'pair_both_correct_rate':pair_both,'pair_ordered_rate':pair_ordered,'cost':cost,'raw_sha256':H(rp),'scope':'train-only pre-commit semantic signal; no task-completion claim','headline_eligible':False};out=R(a.output_dir);(out/'analysis.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# AppWorld A3 — Semantic Write-Signal Result','',f"## Verdict: **`{status}`**",'','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','## Metrics','',f"- Parse rate: {pooled['parse_rate']:.3f}",f"- Balanced accuracy: {pooled['balanced_accuracy']:.3f}",f"- eta_fp: {pooled['eta_fp']:.3f}",f"- eta_fn: {pooled['eta_fn']:.3f}",f"- Pair both-correct rate: {pair_both:.3f}",f"- Type-cluster bootstrap BA CI95: [{ci[0]:.3f}, {ci[1]:.3f}]",'','This is a train-only pre-commit signal anchor, not an end-to-end task-completion result.'];(out/'RESULTS.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'report':str((out/'RESULTS.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
