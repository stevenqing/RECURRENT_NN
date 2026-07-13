"""Frozen shared-GPU runner for AppWorld A4 comparative development prompts."""
from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from analysis.recurrent_appworld_a3_run import H,R
from analysis.recurrent_appworld_a3_contended_run import gpu_query,process_ids
def verify_lock(path):
 lock=json.loads(path.read_text());return lock,{k:H(R(k))==v for k,v in lock['files'].items()}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_comparative_development_v1.json'));ap.add_argument('--manifest',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/prompt_manifest.json'));ap.add_argument('--execution-lock',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/execution_lock.json'));ap.add_argument('--output',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development/raw_model_outputs.json'));a=ap.parse_args();cp,mp,lockp,out=map(R,(a.contract,a.manifest,a.execution_lock,a.output));c=json.loads(cp.read_text());m=json.loads(mp.read_text());lock,lock_checks=verify_lock(lockp);g=c['shared_gpu'];gpu=int(g['physical_gpu']);visible=os.environ.get('CUDA_VISIBLE_DEVICES','');frc,free_text=gpu_query(gpu,'memory.free');prc,pre_pids=process_ids(gpu);free=int(free_text) if free_text.isdigit() else -1;checks={'contract_frozen':c['status']=='FROZEN_BEFORE_COMPARATIVE_MODEL_OUTCOMES','lock_files':all(lock_checks.values()),'contract_hash':H(cp)==lock['contract_sha256'],'manifest_hash':H(mp)==lock['prompt_manifest_sha256'],'model':m['model']==c['model'],'revision':m['model_revision']==c['model_revision'],'user_authorized':g['user_authorized'] is True,'visible_gpu':visible==str(gpu),'free_query':frc==0,'free_memory':free>=g['minimum_free_memory_mib'],'process_query':prc==0,'preexisting_process':bool(pre_pids),'cardinality':len(m['rows'])==c['expected_prompts']}
 if not all(checks.values()):raise RuntimeError(checks)
 import torch
 from transformers import AutoModelForCausalLM,AutoTokenizer
 torch.cuda.set_per_process_memory_fraction(g['memory_fraction_cap'],0);tok=AutoTokenizer.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True);tok.padding_side='left'
 if tok.pad_token_id is None:tok.pad_token=tok.eos_token
 model=AutoModelForCausalLM.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True,torch_dtype=torch.bfloat16).to('cuda:0').eval();rows=[]
 for start in range(0,len(m['rows']),c['batch_size']):
  batch=m['rows'][start:start+c['batch_size']];texts=[]
  for row in batch:texts.append(tok.apply_chat_template([{'role':'system','content':'Choose the better pre-commit candidate and output only JSON.'},{'role':'user','content':row['prompt']}],tokenize=False,add_generation_prompt=True,enable_thinking=c['enable_thinking']))
  enc=tok(texts,return_tensors='pt',padding=True)
  if int(enc['attention_mask'].sum(1).max())>c['max_input_tokens']:raise RuntimeError('input cap')
  enc=enc.to('cuda:0');torch.cuda.synchronize();t0=time.perf_counter()
  with torch.inference_mode():gen=model.generate(**enc,max_new_tokens=c['max_tokens'],do_sample=False,pad_token_id=tok.pad_token_id)
  torch.cuda.synchronize();elapsed=time.perf_counter()-t0;width=enc['input_ids'].shape[1]
  for i,row in enumerate(batch):
   ids=gen[i,width:].tolist();eos={tok.eos_token_id} if isinstance(tok.eos_token_id,int) else set(tok.eos_token_id or []);stop=next((j+1 for j,x in enumerate(ids) if x in eos),len(ids));rows.append({'sample_id':row['sample_id'],'prompt_sha256':row['prompt_sha256'],'output_text':tok.decode(ids[:stop],skip_special_tokens=True).strip(),'prompt_tokens':int(enc['attention_mask'][i].sum()),'output_tokens':stop,'batch_start':start,'batch_size':len(batch),'batch_latency_seconds':elapsed})
 _,post_pids=process_ids(gpu);survival=all(x in post_pids for x in pre_pids);status='RPD_APPWORLD_A4_RAW_COMPLETE' if survival and len(rows)==c['expected_prompts'] else 'RPD_APPWORLD_A4_RAW_PROTOCOL_FAIL';payload={'schema':'recurrent_appworld_a4_raw_v1','status':status,'model':c['model'],'model_revision':c['model_revision'],'generation':{'physical_gpu':gpu,'contended':True,'memory_fraction_cap':g['memory_fraction_cap'],'free_memory_before_mib':free,'preexisting_pids':pre_pids,'post_pids':post_pids,'preexisting_pid_survival':survival,'latency_authoritative':False,'temperature':0,'batch_size':c['batch_size']},'checks':checks,'contract_sha256':H(cp),'manifest_sha256':H(mp),'execution_lock_sha256':H(lockp),'rows':rows};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':status,'rows':len(rows),'external_pid_survival':survival}))
if __name__=='__main__':main()
