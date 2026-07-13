"""Frozen local-Qwen runner for the AppWorld A3 semantic write-signal manifest."""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def verify_lock(p):
 lock=json.loads(p.read_text());items={**{k:(k,v) for k,v in lock['files'].items()},'prompt_manifest':(lock['prompt_manifest']['path'],lock['prompt_manifest']['sha256']),'adjudication_manifest':(lock['adjudication_manifest']['path'],lock['adjudication_manifest']['sha256'])};return lock,{k:H(R(path))==value for k,(path,value) in items.items()}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_signal_anchor_v1.json'));ap.add_argument('--manifest',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/prompt_manifest.json'));ap.add_argument('--execution-lock',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/execution_lock.json'));ap.add_argument('--output',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/raw_model_outputs.json'));ap.add_argument('--device',default='cuda:0');ap.add_argument('--batch-size',type=int,default=8);a=ap.parse_args();cp,mp,ep,out=map(R,(a.contract,a.manifest,a.execution_lock,a.output));c=json.loads(cp.read_text());m=json.loads(mp.read_text());audit=json.loads((mp.parent/'manifest_audit.json').read_text());lock,lock_checks=verify_lock(ep);visible=os.environ.get('CUDA_VISIBLE_DEVICES','');approved={str(x) for x in c['approved_physical_gpus']};processes='UNQUERIED';query_ok=False
 if visible in approved:
  q=subprocess.run(['nvidia-smi','-i',visible,'--query-compute-apps=pid','--format=csv,noheader,nounits'],capture_output=True,text=True,check=False);processes=q.stdout.strip();query_ok=q.returncode==0
 checks={'contract_frozen':c['status']=='FROZEN_BEFORE_PROMPTS_AND_MODEL_OUTCOMES','manifest_ready':audit['status']==c['verdicts']['ready'],'manifest_hash':H(mp)==audit['hashes']['prompt_manifest'],'contract_hash':H(cp)==audit['hashes']['contract'],'execution_lock_hash':H(ep)==audit['hashes']['execution_lock'],'execution_lock_files':all(lock_checks.values()),'model_match':m['model']==c['model']==lock['model'],'revision_match':m['model_revision']==c['model_revision']==lock['model_revision'],'batch_size':a.batch_size==c['batch_size'],'approved_single_gpu':visible in approved and ',' not in visible,'logical_device':a.device=='cuda:0','gpu_query':query_ok,'empty_compute_process_list':processes=='','cardinality':len(m['rows'])==c['selection']['expected_prompts']}
 if not all(checks.values()):raise RuntimeError(checks)
 import torch
 from transformers import AutoModelForCausalLM,AutoTokenizer
 tok=AutoTokenizer.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True);tok.padding_side='left'
 if tok.pad_token_id is None:tok.pad_token=tok.eos_token
 model=AutoModelForCausalLM.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True,torch_dtype=torch.bfloat16).to(a.device).eval();results=[]
 for start in range(0,len(m['rows']),a.batch_size):
  batch=m['rows'][start:start+a.batch_size];texts=[]
  for row in batch:
   messages=[{'role':'system','content':'You are a deterministic pre-commit consistency judge. Output only the exact JSON schema.'},{'role':'user','content':row['prompt']}];texts.append(tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=c['enable_thinking']))
  enc=tok(texts,return_tensors='pt',padding=True)
  if int(enc['attention_mask'].sum(1).max())>c['max_input_tokens']:raise RuntimeError('frozen input token cap exceeded')
  enc=enc.to(a.device);torch.cuda.synchronize();t0=time.perf_counter()
  with torch.inference_mode():generated=model.generate(**enc,max_new_tokens=c['max_tokens'],do_sample=False,pad_token_id=tok.pad_token_id)
  torch.cuda.synchronize();elapsed=time.perf_counter()-t0;width=enc['input_ids'].shape[1]
  for j,row in enumerate(batch):
   ids=generated[j,width:].tolist();eos={tok.eos_token_id} if isinstance(tok.eos_token_id,int) else set(tok.eos_token_id or []);stop=next((i+1 for i,x in enumerate(ids) if x in eos),len(ids));text=tok.decode(ids[:stop],skip_special_tokens=True).strip();results.append({'sample_id':row['sample_id'],'prompt_sha256':row['prompt_sha256'],'output_text':text,'prompt_tokens':int(enc['attention_mask'][j].sum()),'output_tokens':stop,'batch_start':start,'batch_size':len(batch),'batch_latency_seconds':elapsed,'amortized_latency_seconds':elapsed/len(batch)})
  payload={'schema':'recurrent_appworld_a3_raw_outputs_v1','status':'INCOMPLETE' if len(results)<len(m['rows']) else 'RPD_APPWORLD_A3_RAW_COMPLETE','model':c['model'],'model_revision':c['model_revision'],'generation':{'temperature':0,'dtype':c['dtype'],'do_sample':False,'max_tokens':c['max_tokens'],'batch_size':a.batch_size,'device':a.device,'physical_gpu':visible,'preload_compute_processes':processes},'checks':checks,'contract_sha256':H(cp),'manifest_sha256':H(mp),'execution_lock_sha256':H(ep),'rows':results};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':'RPD_APPWORLD_A3_RAW_COMPLETE','rows':len(results),'output':str(out.relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
