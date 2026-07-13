"""Harvest paired AppWorld pre-commit semantic correction prompts on train only."""
from __future__ import annotations
import argparse,collections,hashlib,json,warnings
from pathlib import Path
from experiments.appworld_trace_replay import TraceResolver,canonical,execute_call,mutations_for
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def S(x):return hashlib.sha256(x.encode()).hexdigest()
def compact(value,cfg,depth=0):
 if depth>cfg['max_depth']:return '<TRUNCATED>'
 if isinstance(value,dict):
  out={};blocked=('password','token','card','cvv')
  for key in sorted(value):
   if any(x in key.lower() for x in blocked):continue
   out[key]=compact(value[key],cfg,depth+1)
   if len(out)>=cfg['max_dict_items']:break
  return out
 if isinstance(value,list):return [compact(x,cfg,depth+1) for x in value[:cfg['max_list_items']]]
 if isinstance(value,str):return value[:cfg['max_string_chars']]
 return value
def safe_args(arguments,cfg,priority_fields=()):
 blocked=('password','token','card','cvv');keys=[k for k in sorted(arguments) if not any(x in k.lower() for x in blocked)];priority=[k for k in priority_fields if k in keys];selected=(priority+[k for k in keys if k not in priority])[:cfg['max_dict_items']];output={}
 for key in sorted(selected):
  value=arguments[key]
  if key in priority and isinstance(value,str) and len(value)>cfg['max_string_chars']:
   half=(cfg['max_string_chars']-3)//2;output[key]=value[:half]+'...'+value[-half:]
  else:output[key]=compact(value,cfg,1)
 return output
def select_pairs(dev,cfg):
 strict=[x for x in dev['rows'] if x['outcome']=='semantic_dead' and x['action_succeeded'] and x['suffix_succeeded'] and not x['final_pass']];site={}
 for row in strict:
  key=(row['task_type'],row['call_index'])
  if key not in site or row['mutation_id']<site[key]['mutation_id']:site[key]=row
 groups=collections.defaultdict(list)
 for row in site.values():groups[row['task_type']].append(row)
 selected=[]
 for task_type,rows in sorted(groups.items()):
  ranked=sorted(rows,key=lambda x:S(f"{x['task_type']}|{x['call_index']}|{x['mutation_id']}"));selected+=ranked[:cfg['max_pairs_per_task_type']]
 return sorted(selected,key=lambda x:S(f"{x['task_type']}|{x['call_index']}|{x['mutation_id']}"))
def prompt_text(instruction,history,call,arguments,doc,cfg,priority_fields=()):
 safe_history=[]
 for item in history:
  if any(x in item['api_name'].lower() for x in ('password','token','card','cvv')):continue
  safe_history.append({'app':item['app_name'],'api':item['api_name'],'method':item['method'],'arguments':safe_args(item['arguments'],cfg),'response':compact(item['response'],cfg)})
 safe_history=safe_history[-cfg['history_calls']:];parameter_schema=[]
 for name,p in sorted(call.parameter_docs().items()):
  if any(x in name.lower() for x in ('password','token','card','cvv')):continue
  parameter_schema.append({'name':name,'type':p.get('type'),'required':p.get('required'),'constraints':p.get('constraints') or []})
 payload={'task_goal':instruction,'recent_committed_evidence':safe_history,'candidate_specialist_app':call.app_name,'candidate_api':call.api_name,'candidate_method':call.method.upper(),'api_purpose':doc.get('description',''),'visible_parameter_schema':parameter_schema,'candidate_arguments':safe_args(arguments,cfg,priority_fields)}
 return '\n'.join(['Recurrent app-specialist pre-commit verifier. Return JSON only.','Decide whether this proposed state-mutating API call should be corrected before barrier commit.','Use only the task goal, committed evidence, API documentation, and candidate arguments below.','Schema: {"needs_correction": boolean, "confidence": number between 0 and 1}','Confidence is the probability that your emitted Boolean decision is correct.',canonical(payload)])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_signal_anchor_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_signal_anchor'));a=ap.parse_args();warnings.filterwarnings('ignore');cp=R(a.contract);c=json.loads(cp.read_text());prereqp=R(c['prerequisite']);prereq=json.loads(prereqp.read_text());devp=R(c['development_results']);dev=json.loads(devp.read_text());selected=select_pairs(dev,c['selection'])
 if c.get('status')!='FROZEN_BEFORE_PROMPTS_AND_MODEL_OUTCOMES' or prereq.get('status')!='RPD_APPWORLD_A2_CONTROLLER_PASS':raise ValueError('A3 source not authorized')
 if len(selected)!=c['selection']['expected_pairs'] or len({x['task_type'] for x in selected})!=c['selection']['expected_task_types']:raise RuntimeError('frozen pair cardinality mismatch')
 root=R(c['appworld_root']);from appworld import AppWorld,update_root
 update_root(str(root));by_task=collections.defaultdict(list)
 for row in selected:by_task[row['task_id']].append(row)
 prompts=[];labels=[];verification=[]
 for task_number,(task_id,pairs) in enumerate(sorted(by_task.items())):
  raw=json.loads((root/'data'/'tasks'/task_id/'ground_truth'/'api_calls.json').read_text());spec=json.loads((root/'data'/'tasks'/task_id/'specs.json').read_text());resolver=TraceResolver();calls=resolver.resolve_all(raw);selected_indices={x['call_index'] for x in pairs};mutation_map={}
  for pair in pairs:
   options={x.mutation_id:x for x in mutations_for(calls[pair['call_index']],4)}
   if pair['mutation_id'] not in options:raise RuntimeError('mutation reconstruction failed')
   mutation_map[pair['mutation_id']]=options[pair['mutation_id']]
  world=AppWorld(task_id=task_id,experiment_name=f'a3_harvest_{task_number}',load_ground_truth=True,ground_truth_mode='minimal',raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True);history=[];contexts={};baseline=True
  try:
   for call in calls:
    if call.index in selected_indices:
     world.save_state(f'before_{call.index}');doc=next(x for x in resolver.docs_for(call.app_name) if x['api_name']==call.api_name);contexts[call.index]={'history':list(history),'doc':doc}
    try:response=execute_call(world,call)
    except Exception:baseline=False;break
    history.append({'app_name':call.app_name,'api_name':call.api_name,'method':call.method,'arguments':call.arguments(),'response':response})
   if baseline:
    world._save_state(world.output_db_home_path_on_disk);baseline=world.evaluate().success
   if not baseline:raise RuntimeError('official baseline replay failed')
   for pair in sorted(pairs,key=lambda x:(x['call_index'],x['mutation_id'])):
    call=calls[pair['call_index']];mutation=mutation_map[pair['mutation_id']];world.load_state(f'before_{call.index}');action_ok=True;suffix_ok=True
    try:execute_call(world,call,mutation.arguments())
    except Exception:action_ok=False
    if action_ok:
     for future in calls[call.index+1:]:
      try:execute_call(world,future)
      except Exception:suffix_ok=False;break
    final_pass=False
    if action_ok and suffix_ok:
     world._save_state(world.output_db_home_path_on_disk);final_pass=world.evaluate().success
    if not action_ok or not suffix_ok or final_pass:raise RuntimeError('strict semantic label replay failed')
    shared=contexts[call.index];pair_id=S(f"appworld-a3|{pair['task_type']}|{call.index}|{mutation.mutation_id}");priority=(mutation.field_name,);live_prompt=prompt_text(spec['instruction'],shared['history'],call,call.arguments(),shared['doc'],c['context'],priority);dead_prompt=prompt_text(spec['instruction'],shared['history'],call,mutation.arguments(),shared['doc'],c['context'],priority);context_sha=S(canonical({'instruction':spec['instruction'],'history':shared['history'],'app':call.app_name,'api':call.api_name,'doc':shared['doc'].get('description','')}))
    if live_prompt==dead_prompt:raise RuntimeError('pair prompts are identical after redaction')
    for label,prompt in ((False,live_prompt),(True,dead_prompt)):
     sample_id=S(f'{pair_id}|{int(label)}');prompts.append({'sample_id':sample_id,'pair_id':pair_id,'task_id':task_id,'task_type':pair['task_type'],'prompt':prompt,'prompt_sha256':S(prompt),'context_sha256':context_sha});labels.append({'sample_id':sample_id,'pair_id':pair_id,'task_type':pair['task_type'],'label':label,'call_index':call.index,'mutation_id':mutation.mutation_id if label else None,'action_succeeded':True,'suffix_succeeded':True,'evaluator_passed':not label})
    verification.append({'pair_id':pair_id,'task_type':pair['task_type'],'call_index':call.index,'action_succeeded':action_ok,'suffix_succeeded':suffix_ok,'mutated_evaluator_passed':final_pass})
  finally:AppWorld.close_all()
 prompts.sort(key=lambda x:x['prompt_sha256']);labels.sort(key=lambda x:x['sample_id']);out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);mp=out/'prompt_manifest.json';lp=out/'adjudication_manifest.json';mp.write_text(json.dumps({'schema':'recurrent_appworld_signal_prompt_manifest_v1','status':'HARVESTED_BEFORE_MODEL_OUTCOMES','model':c['model'],'model_revision':c['model_revision'],'protected_local_only':True,'rows':prompts},indent=2,sort_keys=True)+'\n');lp.write_text(json.dumps({'schema':'recurrent_appworld_signal_adjudication_v1','status':'FROZEN_BLINDED_LABELS','rows':labels},indent=2,sort_keys=True)+'\n');checks={'pairs':len(verification)==c['selection']['expected_pairs'],'prompts':len(prompts)==c['selection']['expected_prompts'],'task_types':len({x['task_type'] for x in verification})==c['selection']['expected_task_types'],'balanced':sum(x['label'] for x in labels)*2==len(labels),'strict_replay':all(x['action_succeeded'] and x['suffix_succeeded'] and not x['mutated_evaluator_passed'] for x in verification),'unique_prompts':len({x['prompt_sha256'] for x in prompts})==len(prompts),'labels_separate':all('label' not in x for x in prompts)};payload={'schema':'recurrent_appworld_a3_harvest_v1','status':'APPWORLD_A3_HARVEST_COMPLETE','checks':checks,'pairs':len(verification),'prompts':len(prompts),'task_types':len({x['task_type'] for x in verification}),'hashes':{'contract':H(cp),'prerequisite':H(prereqp),'development':H(devp),'trace_source':H(REPO_ROOT/'experiments/appworld_trace_replay.py'),'harvester':H(Path(__file__)),'prompt_manifest':H(mp),'adjudication_manifest':H(lp)},'verification':verification,'model_outcomes_observed':False,'dev_or_test_read':False,'protected_local_only':True};(out/'harvest.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':payload['status'],'pairs':len(verification),'prompts':len(prompts)}))
if __name__=='__main__':main()
