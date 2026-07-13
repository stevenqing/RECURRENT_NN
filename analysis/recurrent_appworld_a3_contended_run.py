"""Quality-only AppWorld A3 runner on an explicitly authorized contended GPU."""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from analysis.recurrent_appworld_a3_run import H,R,verify_lock
REPO_ROOT=Path(__file__).resolve().parents[1]
def gpu_query(gpu,field):
 p=subprocess.run(['nvidia-smi','-i',str(gpu),f'--query-gpu={field}','--format=csv,noheader,nounits'],capture_output=True,text=True,check=False);return p.returncode,p.stdout.strip()
def process_ids(gpu):
 p=subprocess.run(['nvidia-smi','-i',str(gpu),'--query-compute-apps=pid','--format=csv,noheader,nounits'],capture_output=True,text=True,check=False);return p.returncode,sorted({int(x) for x in p.stdout.split() if x.isdigit()})
def verify_addendum_lock(path):
 lock=json.loads(path.read_text());checks={k:H(R(k))==v for k,v in lock['files'].items()};return lock,checks
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_signal_anchor_v1.json'));ap.add_argument('--addendum',type=Path,default=Path('specs/recurrent_parallel_appworld_signal_contended_execution_v1.json'));ap.add_argument('--manifest',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/prompt_manifest.json'));ap.add_argument('--parent-lock',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/execution_lock.json'));ap.add_argument('--addendum-lock',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/contended_execution_lock.json'));ap.add_argument('--output',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor/raw_model_outputs.json'));a=ap.parse_args();cp,apath,mp,parentp,addlockp,out=map(R,(a.contract,a.addendum,a.manifest,a.parent_lock,a.addendum_lock,a.output));c=json.loads(cp.read_text());add=json.loads(apath.read_text());m=json.loads(mp.read_text());audit=json.loads((mp.parent/'manifest_audit.json').read_text());parent,parent_checks=verify_lock(parentp);addlock,add_checks=verify_addendum_lock(addlockp);physical=int(add['physical_gpu']);visible=os.environ.get('CUDA_VISIBLE_DEVICES','');frc,free_text=gpu_query(physical,'memory.free');prc,pre_pids=process_ids(physical);free_mib=int(free_text) if free_text.isdigit() else -1
 checks={'parent_contract_frozen':c['status']=='FROZEN_BEFORE_PROMPTS_AND_MODEL_OUTCOMES','addendum_frozen':add['status']=='FROZEN_BEFORE_MODEL_OUTCOMES','user_authorized':add['user_authorized_shared_gpu'] is True,'manifest_ready':audit['status']==c['verdicts']['ready'],'parent_lock_files':all(parent_checks.values()),'addendum_lock_files':all(add_checks.values()),'parent_lock_hash':H(parentp)==addlock['parent_execution_lock_sha256'],'contract_hash':H(cp)==addlock['parent_contract_sha256'],'addendum_hash':H(apath)==addlock['addendum_contract_sha256'],'model':m['model']==c['model']==parent['model'],'revision':m['model_revision']==c['model_revision']==parent['model_revision'],'visible_physical_gpu':visible==str(physical),'logical_device':add['logical_device']=='cuda:0','free_memory_query':frc==0,'free_memory':free_mib>=add['minimum_free_memory_mib'],'preexisting_process_query':prc==0,'preexisting_process':bool(pre_pids),'batch_size':add['batch_size']==c['batch_size'],'cardinality':len(m['rows'])==c['selection']['expected_prompts']}
 if not all(checks.values()):raise RuntimeError(checks)
 import torch
 from transformers import AutoModelForCausalLM,AutoTokenizer
 torch.cuda.set_per_process_memory_fraction(float(add['memory_fraction_cap']),device=0);tok=AutoTokenizer.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True);tok.padding_side='left'
 if tok.pad_token_id is None:tok.pad_token=tok.eos_token
 model=AutoModelForCausalLM.from_pretrained(c['model'],revision=c['model_revision'],local_files_only=True,torch_dtype=torch.bfloat16).to('cuda:0').eval();results=[]
 for start in range(0,len(m['rows']),add['batch_size']):
  batch=m['rows'][start:start+add['batch_size']];texts=[]
  for row in batch:
   messages=[{'role':'system','content':'You are a deterministic pre-commit consistency judge. Output only the exact JSON schema.'},{'role':'user','content':row['prompt']}];texts.append(tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=c['enable_thinking']))
  enc=tok(texts,return_tensors='pt',padding=True)
  if int(enc['attention_mask'].sum(1).max())>c['max_input_tokens']:raise RuntimeError('frozen input token cap exceeded')
  enc=enc.to('cuda:0');torch.cuda.synchronize();t0=time.perf_counter()
  with torch.inference_mode():generated=model.generate(**enc,max_new_tokens=c['max_tokens'],do_sample=False,pad_token_id=tok.pad_token_id)
  torch.cuda.synchronize();elapsed=time.perf_counter()-t0;width=enc['input_ids'].shape[1]
  for j,row in enumerate(batch):
   ids=generated[j,width:].tolist();eos={tok.eos_token_id} if isinstance(tok.eos_token_id,int) else set(tok.eos_token_id or []);stop=next((i+1 for i,x in enumerate(ids) if x in eos),len(ids));text=tok.decode(ids[:stop],skip_special_tokens=True).strip();results.append({'sample_id':row['sample_id'],'prompt_sha256':row['prompt_sha256'],'output_text':text,'prompt_tokens':int(enc['attention_mask'][j].sum()),'output_tokens':stop,'batch_start':start,'batch_size':len(batch),'batch_latency_seconds':elapsed,'amortized_latency_seconds':elapsed/len(batch)})
 _,post_pids=process_ids(physical);survival=all(pid in post_pids for pid in pre_pids);status='RPD_APPWORLD_A3_RAW_COMPLETE' if survival and len(results)==len(m['rows']) else 'RPD_APPWORLD_A3_CONTENDED_EXTERNAL_PID_CHANGED';payload={'schema':'recurrent_appworld_a3_raw_outputs_v1','status':status,'model':c['model'],'model_revision':c['model_revision'],'generation':{'temperature':0,'dtype':c['dtype'],'do_sample':False,'max_tokens':c['max_tokens'],'batch_size':add['batch_size'],'device':'cuda:0','physical_gpu':physical,'contended':True,'memory_fraction_cap':add['memory_fraction_cap'],'free_memory_before_mib':free_mib,'preexisting_pids':pre_pids,'post_pids':post_pids,'preexisting_pid_survival':survival,'latency_authoritative':False},'checks':checks,'contract_sha256':H(cp),'manifest_sha256':H(mp),'execution_lock_sha256':H(parentp),'execution_addendum_sha256':H(apath),'contended_execution_lock_sha256':H(addlockp),'rows':results};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':status,'rows':len(results),'external_pid_survival':survival,'output':str(out.relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
