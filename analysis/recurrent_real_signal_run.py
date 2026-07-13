"""Frozen local-HuggingFace runner for the recurrent real-signal prompt manifest.

Do not execute while approved GPUs are occupied by external processes.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path
from experiments.multiagent_capacity_coupling import REPO_ROOT
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_lock(p):
 lock=json.loads(p.read_text());locked={**{x:(x,h) for x,h in lock['files'].items()},'prompt_manifest':(lock['prompt_manifest']['path'],lock['prompt_manifest']['sha256']),'adjudication_manifest':(lock['adjudication_manifest']['path'],lock['adjudication_manifest']['sha256'])};checks={name:H(R(path))==digest for name,(path,digest) in locked.items()};return lock,checks
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor/prompt_manifest.json'));ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_real_signal_anchor_v1.json'));ap.add_argument('--execution-lock',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor/execution_lock.json'));ap.add_argument('--output',type=Path,default=Path('results/recurrent_parallel_real_signal_anchor/raw_model_outputs.json'));ap.add_argument('--device',default='cuda:0');ap.add_argument('--batch-size',type=int,default=8);a=ap.parse_args();mp,cp,out=R(a.manifest),R(a.contract),R(a.output);c=json.loads(cp.read_text());m=json.loads(mp.read_text());audit=json.loads((mp.parent/'manifest_audit.json').read_text());lock,lock_checks=verify_lock(R(a.execution_lock));visible=os.environ.get('CUDA_VISIBLE_DEVICES','');approved={str(x) for x in c['approved_physical_gpus']};gpu_processes='UNQUERIED'
 if visible in approved:
  query=subprocess.run(['nvidia-smi','-i',visible,'--query-compute-apps=pid','--format=csv,noheader,nounits'],capture_output=True,text=True,check=False);gpu_processes=query.stdout.strip();gpu_query_ok=query.returncode==0
 else:gpu_query_ok=False
 checks={'contract_frozen':c.get('status')=='FROZEN_BEFORE_MODEL_OUTCOMES','manifest_frozen':m.get('status')=='RPD_REAL_SIGNAL_PROMPT_MANIFEST_FROZEN','manifest_hash':H(mp)==audit['hashes']['manifest'],'contract_hash':H(cp)==audit['hashes']['contract'],'execution_lock_hash':H(R(a.execution_lock))==audit['hashes']['execution_lock'],'execution_lock_files':all(lock_checks.values()),'model_match':m.get('model')==c.get('model')==lock.get('model'),'revision_match':m.get('model_revision')==c.get('model_revision')==lock.get('model_revision'),'local_only':c.get('local_files_only') is True,'dtype':c.get('dtype')=='bfloat16','batch_size':a.batch_size==c.get('batch_size'),'approved_single_gpu':visible in approved and ',' not in visible,'logical_device':a.device=='cuda:0','gpu_query':gpu_query_ok,'empty_compute_process_list':gpu_processes=='','cardinality':len(m.get('rows',[]))==c.get('expected_prompts')==lock.get('expected_prompts')}
 if not all(checks.values()):raise RuntimeError(checks)
 import torch
 from transformers import AutoModelForCausalLM,AutoTokenizer
 tok=AutoTokenizer.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True);tok.padding_side='left'
 if tok.pad_token_id is None:tok.pad_token=tok.eos_token
 model=AutoModelForCausalLM.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True,torch_dtype=torch.bfloat16).to(a.device).eval();results=[]
 for start in range(0,len(m['rows']),a.batch_size):
  batch=m['rows'][start:start+a.batch_size];texts=[]
  for r in batch:
    msgs=[{'role':'system','content':'You are a deterministic local consistency judge. Obey the exact JSON schema and output no explanation.'},{'role':'user','content':r['prompt']}];texts.append(tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True,enable_thinking=c['enable_thinking']))
  enc=tok(texts,return_tensors='pt',padding=True)
  if int(enc['attention_mask'].sum(1).max())>int(c['max_input_tokens']):raise RuntimeError('frozen input token cap exceeded')
  enc=enc.to(a.device);torch.cuda.synchronize() if str(a.device).startswith('cuda') else None;t0=time.perf_counter()
  with torch.inference_mode():gen=model.generate(**enc,max_new_tokens=int(c['max_tokens']),do_sample=False,pad_token_id=tok.pad_token_id or tok.eos_token_id)
  torch.cuda.synchronize() if str(a.device).startswith('cuda') else None;elapsed=time.perf_counter()-t0;prompt_width=enc['input_ids'].shape[1]
  for j,r in enumerate(batch):
    new=gen[j,prompt_width:];ids=new.tolist();eos={tok.eos_token_id} if isinstance(tok.eos_token_id,int) else set(tok.eos_token_id or [])
    stop=next((z+1 for z,x in enumerate(ids) if x in eos),len(ids));text=tok.decode(ids[:stop],skip_special_tokens=True).strip();results.append({'sample_id':r['sample_id'],'prompt_sha256':r['prompt_sha256'],'output_text':text,'prompt_tokens':int(enc['attention_mask'][j].sum()),'output_tokens':stop,'batch_start':start,'batch_latency_seconds':elapsed,'amortized_latency_seconds':elapsed/len(batch),'batch_size':len(batch)})
  payload={'schema':'recurrent_real_signal_raw_outputs_v1','status':'INCOMPLETE' if len(results)<len(m['rows']) else 'RPD_REAL_SIGNAL_RAW_COMPLETE','model':c['model'],'model_revision':c['model_revision'],'generation':{'temperature':c['temperature'],'dtype':c['dtype'],'max_tokens':c['max_tokens'],'do_sample':False,'device':a.device,'physical_gpu':visible,'batch_size':a.batch_size,'preload_compute_processes':gpu_processes},'checks':checks,'manifest_sha256':H(mp),'contract_sha256':H(cp),'execution_lock_sha256':H(R(a.execution_lock)),'rows':results};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'RPD_REAL_SIGNAL_RAW_COMPLETE','rows':len(results),'output':str(out.relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
