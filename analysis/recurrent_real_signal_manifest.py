"""Freeze balanced deployment-visible recurrent correction prompts for Qwen."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.recurrent_signal_prompts import harvest_graph,harvest_sat,visible_correction_label
SCHEMA='recurrent_parallel_real_signal_anchor_contract_v1'
def R(p):
 v=Path(p);return v if v.is_absolute() else REPO_ROOT/v
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_real_signal_anchor_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor'));a=ap.parse_args();cp=R(a.contract);c=json.loads(cp.read_text())
 if c.get('schema')!=SCHEMA or c.get('status')!='FROZEN_BEFORE_MODEL_OUTCOMES':raise ValueError('anchor contract not frozen')
 errp=R(c['prerequisite_erratum']);err=json.loads(errp.read_text());
 if err.get('corrected_status')!='RPD_COST_SENSITIVE_CROSS_SUBSTRATE_CONFIRMATION_PASS':raise ValueError('anchor prerequisite failed')
 pools={'graph':list(json.loads(R(c['graph_manifest']).read_text())['rows']),'sat':list(json.loads(R(c['sat_manifest']).read_text())['rows'])};allrows=[]
 for sub,instances in pools.items():
  fn=harvest_graph if sub=='graph' else harvest_sat
  for i,inst in enumerate(instances):allrows+=fn(inst)
 dedup={r['prompt_sha256']:r for r in allrows};selected=[];n=int(c['samples_per_cell'])
 for sub in ('graph','sat'):
  for d in (2,4,8,16):
   for label in (False,True):
    pool=sorted([r for r in dedup.values() if r['substrate']==sub and r['partition_diameter']==d and r['label']==label],key=lambda r:r['prompt_sha256'])
    chosen=[];used=set()
    for r in pool:
     if r['instance_id'] in used:continue
     chosen.append(r);used.add(r['instance_id'])
     if len(chosen)==n:break
    if len(chosen)<n:raise RuntimeError(f'insufficient independent {sub} d{d} label{label}: {len(chosen)}')
    selected+=chosen
 for i,r in enumerate(selected):r['sample_id']=f"anchor_{i:04d}_{r['substrate']}_d{r['partition_diameter']}_{'dead' if r['label'] else 'live'}"
 forbidden=c['forbidden_prompt_fields'];checks={'count':len(selected)==c['expected_prompts'],'unique_ids':len({r['sample_id'] for r in selected})==len(selected),'unique_prompts':len({r['prompt_sha256'] for r in selected})==len(selected),'balanced':all(sum(r['substrate']==s and r['partition_diameter']==d and r['label']==lab for r in selected)==n for s in ('graph','sat') for d in (2,4,8,16) for lab in (False,True)),'independent_instances':all(len({r['instance_id'] for r in selected if r['substrate']==s and r['partition_diameter']==d and r['label']==lab})==n for s in ('graph','sat') for d in (2,4,8,16) for lab in (False,True)),'visible_label_replay':all(visible_correction_label(r['prompt'],r['substrate'])==r['label'] for r in selected),'no_forbidden':all(not any(f in r['prompt'] for f in forbidden) for r in selected),'no_planted':all('planted' not in r['prompt'].lower() for r in selected)}
 if not all(checks.values()):raise RuntimeError(checks)
 public=[];labels=[]
 for r in selected:
  labels.append({k:r[k] for k in ('sample_id','prompt_sha256','substrate','partition_diameter','label')});public.append({k:v for k,v in r.items() if k!='label'})
 checks['blinded_labels']=all('label' not in r for r in public) and len(labels)==len(public)
 from transformers import AutoTokenizer
 tok=AutoTokenizer.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True);formatted=[]
 for r in public:
  messages=[{'role':'system','content':'You are a deterministic local consistency judge. Obey the exact JSON schema and output no explanation.'},{'role':'user','content':r['prompt']}]
  formatted.append(tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=c['enable_thinking']))
 prompt_tokens=[len(tok(x)['input_ids']) for x in formatted];checks['input_token_cap']=max(prompt_tokens)<=c['max_input_tokens']
 if not all(checks.values()):raise RuntimeError(checks)
 out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);mp=out/'prompt_manifest.json';mp.write_text(json.dumps({'schema':'recurrent_real_signal_prompt_manifest_v1','status':'RPD_REAL_SIGNAL_PROMPT_MANIFEST_FROZEN','model':c['model'],'model_revision':c['model_revision'],'rows':public},indent=2,sort_keys=True)+'\n');labelp=out/'adjudication_manifest.json';labelp.write_text(json.dumps({'schema':'recurrent_real_signal_adjudication_manifest_v1','status':'FROZEN_BLINDED_LABELS','rows':labels},indent=2,sort_keys=True)+'\n')
 lock_paths=['specs/recurrent_parallel_real_signal_anchor_v1.md','specs/recurrent_parallel_real_signal_anchor_v1.json',c['prerequisite_erratum'],c['graph_manifest'],c['sat_manifest'],'specs/recurrent_parallel_cost_sensitive_confirmation_v1.json','results/model_download/qwen3_5_4b/qwen_download.json','experiments/recurrent_parallel_core.py','experiments/recurrent_parallel_sat_core.py','experiments/recurrent_signal_prompts.py','analysis/recurrent_real_signal_manifest.py','analysis/recurrent_real_signal_run.py','analysis/recurrent_real_signal_analysis.py']
 lock={'schema':'recurrent_real_signal_execution_lock_v1','status':'EXECUTION_LOCKED_BEFORE_MODEL_OUTCOMES','files':{p:H(R(p)) for p in lock_paths},'prompt_manifest':{'path':str(mp.relative_to(REPO_ROOT)),'sha256':H(mp)},'adjudication_manifest':{'path':str(labelp.relative_to(REPO_ROOT)),'sha256':H(labelp)},'model':c['model'],'model_revision':c['model_revision'],'expected_prompts':c['expected_prompts']};lockp=out/'execution_lock.json';lockp.write_text(json.dumps(lock,indent=2,sort_keys=True)+'\n')
 payload={'schema':'recurrent_real_signal_manifest_audit_v1','status':'RPD_REAL_SIGNAL_ANCHOR_READY_BLOCKED_GPU','checks':checks,'harvested':len(allrows),'deduplicated':len(dedup),'selected':len(selected),'prompt_tokens':{'minimum':min(prompt_tokens),'mean':sum(prompt_tokens)/len(prompt_tokens),'maximum':max(prompt_tokens),'cap':c['max_input_tokens']},'cell_counts':{str(k):v for k,v in Counter((r['substrate'],r['partition_diameter'],r['label']) for r in selected).items()},'hashes':{'manifest':H(mp),'adjudication_manifest':H(labelp),'execution_lock':H(lockp),'contract':H(cp),'erratum':H(errp),'harvester':H(REPO_ROOT/'experiments/recurrent_signal_prompts.py'),'source':H(Path(__file__))},'gpu_status':'blocked_external_processes','headline_eligible':False}
 (out/'manifest_audit.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# Frozen-Qwen Recurrent Signal Anchor — Offline Manifest','',f"## Status: **`{payload['status']}`**",'',f"- Harvested states: {payload['harvested']}",f"- Deduplicated prompts: {payload['deduplicated']}",f"- Frozen balanced prompts: {payload['selected']}",f"- Formatted prompt tokens: {payload['prompt_tokens']['minimum']}–{payload['prompt_tokens']['maximum']} (mean {payload['prompt_tokens']['mean']:.1f})",'- Adjudication labels: separate hash-locked manifest','- Model outcomes observed: No','- GPU launch: blocked by external jobs','','## Checks','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in checks.items()]+['','The model runner is implemented separately. Do not regenerate or resample prompts after model outcomes.']
 (out/'MANIFEST.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':payload['status'],'prompts':len(selected),'manifest_sha256':payload['hashes']['manifest'],'report':str((out/'MANIFEST.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
