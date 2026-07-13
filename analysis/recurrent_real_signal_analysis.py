"""Frozen scoring and phase-law placement for the real recurrent signal anchor."""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from statistics import mean
from analysis.recurrent_real_signal_run import verify_lock
from experiments.multiagent_capacity_coupling import REPO_ROOT
FAIL=5000
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parse(text):
 try:
  x=json.loads(text)
  if not isinstance(x,dict) or set(x)!={'needs_correction','confidence'} or type(x['needs_correction']) is not bool or type(x['confidence']) not in (int,float) or isinstance(x['confidence'],bool) or not math.isfinite(float(x['confidence'])) or not 0<=float(x['confidence'])<=1:return None
  return bool(x['needs_correction']),float(x['confidence'])
 except (json.JSONDecodeError,TypeError,ValueError):return None
def binom_cdf(k,n,p):return sum(math.comb(n,i)*p**i*(1-p)**(n-i) for i in range(k+1))
def cp(errors,total,alpha=.05):
 if total<=0:return [float('nan'),float('nan')]
 if errors==0:lo=0.0
 else:
  a,b=0.0,errors/total
  for _ in range(80):
   q=(a+b)/2
   if 1-binom_cdf(errors-1,total,q)<alpha/2:a=q
   else:b=q
  lo=b
 if errors==total:hi=1.0
 else:
  a,b=errors/total,1.0
  for _ in range(80):
   q=(a+b)/2
   if binom_cdf(errors,total,q)>alpha/2:a=q
   else:b=q
  hi=b
 return [lo,hi]
def metrics(rows):
 valid=[r for r in rows if r['parsed']];live=[r for r in rows if not r['label']];dead=[r for r in rows if r['label']];fp_errors=sum(not r['parsed'] or bool(r['prediction']) for r in live);fn_errors=sum(not r['parsed'] or not bool(r['prediction']) for r in dead);fp=fp_errors/len(live) if live else float('nan');fn=fn_errors/len(dead) if dead else float('nan');bal=1-(fp+fn)/2;p=[r['confidence'] if r['prediction'] else 1-r['confidence'] for r in valid];brier=(sum((q-float(r['label']))**2 for q,r in zip(p,valid))+len(rows)-len(valid))/len(rows) if rows else float('nan');ece=0.0
 for lo,hi in zip((0,.2,.4,.6,.8),(.2,.4,.6,.8,1.0)):
  z=[(q,r) for q,r in zip(p,valid) if lo<=q<(hi if hi<1 else hi+1e-12)]
  if z:ece+=len(z)/len(valid)*abs(mean(q for q,_ in z)-mean(float(r['label']) for _,r in z))
 return {'n':len(rows),'valid':len(valid),'parse_rate':len(valid)/len(rows) if rows else 0,'eta_fp':fp,'eta_fp_errors':fp_errors,'eta_fp_trials':len(live),'eta_fp_ci95':cp(fp_errors,len(live)),'eta_fn':fn,'eta_fn_errors':fn_errors,'eta_fn_trials':len(dead),'eta_fn_ci95':cp(fn_errors,len(dead)),'balanced_accuracy':bal,'brier':brier,'ece_5bin_valid':ece}
def objective(k,e,x):return x['live']*sum(e**j for j in range(k))+x['dead']*k+FAIL*(1-(1-e**k)**x['live'])
def choose(e,x):return min(range(1,9),key=lambda k:(objective(k,e,x),k))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--raw',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor/raw_model_outputs.json'));ap.add_argument('--manifest',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor/prompt_manifest.json'));ap.add_argument('--labels',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor/adjudication_manifest.json'));ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_real_signal_anchor_v1.json'));ap.add_argument('--cost-contract',type=Path,default=Path('specs/recurrent_parallel_cost_sensitive_confirmation_v1.json'));ap.add_argument('--execution-lock',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor/execution_lock.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor'));a=ap.parse_args();rp,mp,labelp,cp,kp=map(R,(a.raw,a.manifest,a.labels,a.contract,a.cost_contract));lp=R(a.execution_lock);raw=json.loads(rp.read_text());manifest=json.loads(mp.read_text());adjudication=json.loads(labelp.read_text());c=json.loads(cp.read_text());cost=json.loads(kp.read_text());_,lock_checks=verify_lock(lp);prompts={r['sample_id']:r for r in manifest['rows']};labels={r['sample_id']:r for r in adjudication['rows']};truth={sid:{**p,**labels[sid]} for sid,p in prompts.items() if sid in labels};outputs={r['sample_id']:r for r in raw['rows']}
 integrity={'raw_complete':raw.get('status')=='RPD_REAL_SIGNAL_RAW_COMPLETE','model_match':raw.get('model')==c.get('model'),'revision_match':raw.get('model_revision')==c.get('model_revision'),'manifest_hash':raw.get('manifest_sha256')==H(mp),'contract_hash':raw.get('contract_sha256')==H(cp),'execution_lock_hash':raw.get('execution_lock_sha256')==H(lp),'execution_lock_files':all(lock_checks.values()),'blinded_labels':c.get('label_manifest_blinded') is True and set(prompts)==set(labels) and all('label' not in r for r in manifest['rows']),'raw_cardinality':len(raw.get('rows',[]))==c['expected_prompts'],'unique_outputs':len(outputs)==len(raw.get('rows',[])),'exact_ids':set(outputs)==set(truth),'prompt_hashes':all(outputs[x].get('prompt_sha256')==truth[x]['prompt_sha256'] for x in set(outputs)&set(truth))}
 rows=[]
 for sid,t in truth.items():
  o=outputs.get(sid,{});z=parse(o.get('output_text',''));rows.append({'sample_id':sid,'substrate':t['substrate'],'diameter':t['partition_diameter'],'label':t['label'],'parsed':z is not None,'prediction':z[0] if z else None,'confidence':z[1] if z else None})
 pooled=metrics(rows);groups={'pooled':pooled}
 for sub in ('graph','sat'):groups[sub]=metrics([r for r in rows if r['substrate']==sub])
 for sub in ('graph','sat'):
  for d in (2,4,8,16):groups[f'{sub}_d{d}']=metrics([r for r in rows if r['substrate']==sub and r['diameter']==d])
 placements={}
 for sub in ('graph','sat'):
    placements[sub]={}
    for d in (2,4,8,16):
     z=groups[f'{sub}_d{d}'];e=z['eta_fp'];lo,hi=z['eta_fp_ci95']
     if math.isfinite(e):placements[sub][str(d)]={'eta_fp':e,'eta_fp_ci95':[lo,hi],'k_point':choose(e,cost['exposures'][sub][str(d)]),'k_ci95':[choose(lo,cost['exposures'][sub][str(d)]),choose(hi,cost['exposures'][sub][str(d)])],'objectives':{str(k):objective(k,e,cost['exposures'][sub][str(d)]) for k in range(1,9)}}
 a0=all(integrity.values());a1=pooled['parse_rate']>=.95;a2=all(groups[x]['balanced_accuracy']>=.70 and groups[x]['eta_fp']<.40 and groups[x]['eta_fn']<.40 for x in ('pooled','graph','sat'));a3=pooled['brier']<.25 and pooled['ece_5bin_valid']<=.15;a4=all(len(placements[s])==4 for s in ('graph','sat'));gates={'A0_manifest_integrity':a0,'A1_generation':a1,'A2_signal_quality':a2,'A3_calibration':a3,'A4_cost_placement':a4}
 if not a0:status='RPD_REAL_SIGNAL_ANCHOR_PROTOCOL_FAIL'
 elif all(gates.values()):status='RPD_REAL_SIGNAL_ANCHOR_PASS'
 else:status='RPD_REAL_SIGNAL_ANCHOR_MODEL_FAIL'
 batches={r['batch_start']:r for r in raw['rows']};costs={'prompt_tokens':sum(r['prompt_tokens'] for r in raw['rows']),'output_tokens':sum(r['output_tokens'] for r in raw['rows']),'total_tokens':sum(r['prompt_tokens']+r['output_tokens'] for r in raw['rows']),'total_generation_seconds':sum(r['batch_latency_seconds'] for r in batches.values()),'mean_amortized_latency_seconds':mean(r['amortized_latency_seconds'] for r in raw['rows'])}
 payload={'schema':'recurrent_real_signal_anchor_analysis_v1','status':status,'headline_eligible':False,'integrity':integrity,'gates':gates,'metrics':groups,'cost_placement':placements,'measured_model_cost':costs,'raw_sha256':H(rp),'manifest_sha256':H(mp),'contract_sha256':H(cp),'scope':'development anchor; no end-to-end real-judge recurrence claim'};out=R(a.output_dir);(out/'analysis.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# Frozen-Qwen Recurrent Signal Anchor','',f'## Verdict: **`{status}`**','','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','## Signal metrics','','| Scope | Parse | eta_fp | eta_fn | Balanced accuracy | Brier | ECE |','|---|---:|---:|---:|---:|---:|---:|']
 for key in ('pooled','graph','sat'):x=groups[key];lines.append(f"| {key} | {x['parse_rate']:.3f} | {x['eta_fp']:.3f} | {x['eta_fn']:.3f} | {x['balanced_accuracy']:.3f} | {x['brier']:.3f} | {x['ece_5bin_valid']:.3f} |")
 lines+=['','This is a development signal anchor. It does not establish end-to-end LLM-agent benefit.'];(out/'RESULTS.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'report':str((out/'RESULTS.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
