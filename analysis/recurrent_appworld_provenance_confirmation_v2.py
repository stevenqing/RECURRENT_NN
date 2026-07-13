"""Untouched-dev provenance confirmation with current-replay token rebinding."""
from __future__ import annotations
import argparse,collections,json,math,warnings
from pathlib import Path
from experiments.appworld_provenance import candidate_evidence,deterministic_choice
from experiments.appworld_trace_replay import TraceResolver,execute_call,mutations_for
from analysis.recurrent_appworld_provenance_confirmation import H,R,S,binomial_p
REPO_ROOT=Path(__file__).resolve().parents[1]
def execute_runtime(world,call,tokens,arguments=None):
 args=dict(call.arguments() if arguments is None else arguments)
 if 'access_token' in args and call.app_name in tokens:args['access_token']=tokens[call.app_name]
 response=execute_call(world,call,args)
 if isinstance(response,dict) and isinstance(response.get('access_token'),str):tokens[call.app_name]=response['access_token']
 return response
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_provenance_confirmation_v2.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_provenance_confirmation_v2'));a=ap.parse_args();warnings.filterwarnings('ignore');cp=R(a.contract);c=json.loads(cp.read_text());devp=R(c['development_result']);dev=json.loads(devp.read_text());failure=json.loads(R(c['v1_failure']).read_text());public=json.loads(R(c['candidate_manifest']).read_text())['rows'];protected=json.loads(R(c['adjudication_manifest']).read_text())['rows'];lockp=R(c['execution_lock']);lock=json.loads(lockp.read_text());lock_checks={p:H(R(p))==h for p,h in lock['files'].items()}
 if c['status']!='FROZEN_BEFORE_DEV_GUARD_OUTCOMES' or dev['status']!='RPD_APPWORLD_A4_DETERMINISTIC_PROVENANCE_GO' or failure['status']!='RPD_APPWORLD_A5_V1_REPLAY_PROTOCOL_FAIL' or failure['guard_outcomes_observed']!=0 or not all(lock_checks.values()):raise ValueError('v2 source or lock invalid')
 keys={x['task_id']:x['selection_key'] for x in public};source=[{**x,'selection_key':keys[x['task_id']]} for x in protected if x['split']==c['split']];groups=collections.defaultdict(list)
 for row in source:groups[row['task_type']].append(row)
 selected_tasks=[min(z,key=lambda x:x['selection_key']) for _,z in sorted(groups.items())]
 if len(selected_tasks)!=c['expected_source_task_types']:raise RuntimeError('dev type cardinality mismatch')
 root=R(c['appworld_root']);from appworld import AppWorld,update_root
 update_root(str(root));strict=[];task_summaries=[];histories={};token_snapshots={};calls_by_task={}
 for task_number,row in enumerate(selected_tasks):
  task_id=row['task_id'];calls=TraceResolver().resolve_all(json.loads((root/'data'/'tasks'/task_id/'ground_truth'/'api_calls.json').read_text()));calls_by_task[task_id]=calls;mutations=[]
  for call in calls:
   if call.method=='get' or call.app_name in {'supervisor','api_docs'} or any(x in call.api_name.lower() for x in ('login','auth','token')):continue
   mutations.extend(mutations_for(call,4))
  mutations=sorted(mutations,key=lambda x:x.mutation_id)[:c['max_mutations_per_task']];indices={x.call_index for x in mutations};world=AppWorld(task_id=task_id,experiment_name=f'a5_v2_confirm_{task_number}',load_ground_truth=True,ground_truth_mode='minimal',raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True);history=[];tokens={};baseline=True;baseline_error=None
  try:
   for call in calls:
    if call.index in indices:world.save_state(f'before_{call.index}');histories[(task_id,call.index)]=list(history);token_snapshots[(task_id,call.index)]=dict(tokens)
    try:response=execute_runtime(world,call,tokens)
    except Exception as exc:baseline=False;baseline_error={'call_index':call.index,'error_type':type(exc).__name__};break
    history.append({'call_index':call.index,'app_name':call.app_name,'api_name':call.api_name,'method':call.method,'arguments':call.arguments(),'response':response})
   if baseline:world._save_state(world.output_db_home_path_on_disk);baseline=world.evaluate().success
   if baseline:
    for mutation in mutations:
     world.load_state(f'before_{mutation.call_index}');branch_tokens=dict(token_snapshots[(task_id,mutation.call_index)]);action=True;suffix=True
     try:execute_runtime(world,calls[mutation.call_index],branch_tokens,mutation.arguments())
     except Exception:action=False
     if action:
      for future in calls[mutation.call_index+1:]:
       try:execute_runtime(world,future,branch_tokens)
       except Exception:suffix=False;break
     final=False
     if action and suffix:world._save_state(world.output_db_home_path_on_disk);final=world.evaluate().success
     if action and suffix and not final:strict.append({'task_id':task_id,'task_type':row['task_type'],'call_index':mutation.call_index,'mutation_id':mutation.mutation_id,'mutation':mutation})
  finally:AppWorld.close_all()
  task_summaries.append({'task_id':task_id,'task_type':row['task_type'],'baseline_pass':baseline,'baseline_error':baseline_error,'candidate_mutations':len(mutations)})
 sites={}
 for row in strict:
  key=(row['task_type'],row['call_index'])
  if key not in sites or row['mutation_id']<sites[key]['mutation_id']:sites[key]=row
 site_groups=collections.defaultdict(list)
 for row in sites.values():site_groups[row['task_type']].append(row)
 selected=[]
 for task_type,z in sorted(site_groups.items()):selected+=sorted(z,key=lambda x:S(f"{x['task_type']}|{x['call_index']}|{x['mutation_id']}"))[:c['max_pairs_per_task_type']]
 results=[];cfg=c['provenance']
 for row in sorted(selected,key=lambda x:S(f"{x['task_type']}|{x['call_index']}|{x['mutation_id']}")):
  call=calls_by_task[row['task_id']][row['call_index']];live=call.arguments();dead=row['mutation'].arguments();fields=sorted(k for k in set(live)|set(dead) if live.get(k)!=dead.get(k));history=histories[(row['task_id'],row['call_index'])];goal=json.loads((root/'data'/'tasks'/row['task_id']/'specs.json').read_text())['instruction'];live_e=candidate_evidence(live,fields,history,goal,cfg,cfg['max_citations_per_field_candidate']);dead_e=candidate_evidence(dead,fields,history,goal,cfg,cfg['max_citations_per_field_candidate']);pair=S(f"a5v2|{row['task_type']}|{row['call_index']}|{row['mutation_id']}");live_a=int(pair,16)%2==0;ea,eb=(live_e,dead_e) if live_a else (dead_e,live_e);preferred='A' if live_a else 'B';choice=deterministic_choice(ea,eb);results.append({'pair_id':pair,'task_id':row['task_id'],'task_type':row['task_type'],'call_index':row['call_index'],'support_A':ea['support_count'],'support_B':eb['support_count'],'preferred':preferred,'choice':choice,'covered':choice is not None,'correct':choice==preferred if choice else None})
 covered=[x for x in results if x['covered']];correct=sum(bool(x['correct']) for x in covered);wrong=len(covered)-correct;coverage=len(covered)/len(results) if results else 0;accuracy=correct/len(covered) if covered else 0;pvalue=binomial_p(correct,len(covered));v0=all(x['baseline_pass'] for x in task_summaries);v1=len(results)>=10 and len({x['task_type'] for x in results})>=5;v2=coverage>=.50;v3=wrong==0;v4=accuracy>=.80 and pvalue<.05;forbidden={'required_app_names','instruction','evidence','api_calls','solution','evaluation'};v5=all(not (set(x)&forbidden) for x in results);gates={'V0_integrity':v0,'V1_yield':v1,'V2_coverage':v2,'V3_safety':v3,'V4_evidence':v4,'V5_scope':v5}
 if not v0 or not v5:status=c['verdicts']['protocol']
 elif all(gates.values()):status=c['verdicts']['pass']
 else:status=c['verdicts']['no_go']
 out=R(a.output_dir);rawp=out/'results.json';payload={'schema':'recurrent_appworld_provenance_confirmation_v2','status':status,'gates':gates,'source_task_types':len(selected_tasks),'strict_pairs':len(results),'strict_task_types':len({x['task_type'] for x in results}),'coverage':coverage,'covered':len(covered),'correct':correct,'wrong':wrong,'covered_accuracy':accuracy,'binomial_p_one_sided':pvalue,'task_summaries':task_summaries,'rows':results,'runtime_token_rebinding':True,'execution_lock_sha256':H(lockp),'v1_failure_preserved':H(R(c['v1_failure'])),'dev_only':True,'test_model_gpu_docker_used':False,'headline_eligible':False};rawp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');(out/'result_binding.json').write_text(json.dumps({'schema':'recurrent_appworld_a5_v2_result_binding','execution_lock_sha256':H(lockp),'results_sha256':H(rawp)},indent=2,sort_keys=True)+'\n');lines=['# AppWorld A5 v2 — Deterministic Provenance Confirmation','',f"## Verdict: **`{status}`**",'',f"- Strict dev pairs: {len(results)}",f"- Dev task types represented: {len({x['task_type'] for x in results})}/{len(selected_tasks)}",f"- Coverage: {coverage:.3f}",f"- Covered accuracy: {accuracy:.3f}",f"- Incorrect covered choices: {wrong}",f"- Exact one-sided binomial p: {pvalue:.6f}",'- Runtime token rebinding: enabled','- Pre-outcome execution lock: verified','- Model/GPU/Docker/test used: No','','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','A pass confirms a selective deterministic provenance guard on untouched dev task types. It does not establish end-to-end task-completion improvement.'];(out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'pairs':len(results),'coverage':coverage,'accuracy':accuracy,'p':pvalue,'report':str((out/'REPORT.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
