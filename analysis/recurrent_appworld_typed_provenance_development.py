"""Reserved-train-variation development of typed provenance on native live traces."""
from __future__ import annotations
import argparse,collections,json,warnings
from dataclasses import asdict
from pathlib import Path
from experiments.appworld_live_trace import LiveTraceRecorder
from experiments.appworld_provenance import candidate_evidence,deterministic_choice
from experiments.appworld_typed_provenance import candidate_typed_evidence,typed_choice
from experiments.appworld_trace_replay import ResolvedCall,TraceResolver,canonical,mutations_for
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def S(x):
 import hashlib
 return hashlib.sha256(x.encode()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_typed_provenance_development_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_typed_provenance_development'));a=ap.parse_args();warnings.filterwarnings('ignore');c=json.loads(R(a.contract).read_text());public=json.loads(R(c['a1_candidate_manifest']).read_text())['rows'];protected=json.loads(R(c['a1_adjudication_manifest']).read_text())['rows'];a3=json.loads(R(c['a3_development']).read_text());used={x['task_type']:x['task_id'] for x in a3['task_summary']};keys={x['task_id']:x['selection_key'] for x in public};rows=[{**x,'selection_key':keys[x['task_id']]} for x in protected if x['split']==c['split']];groups=collections.defaultdict(list)
 for row in rows:
  if row['task_id']!=used.get(row['task_type']):groups[row['task_type']].append(row)
 selected_tasks=[min(z,key=lambda x:x['selection_key']) for _,z in sorted(groups.items())]
 if c['status']!='FROZEN_BEFORE_RESERVED_VARIATION_OUTCOMES' or len(selected_tasks)!=c['expected_task_types']:raise ValueError('typed development source mismatch')
 root=R(c['appworld_root']);from appworld import AppWorld,update_root
 update_root(str(root));strict=[];task_summaries=[];history_by_site={};calls_by_task={};mutations_by_id={}
 for task_number,row in enumerate(selected_tasks):
  task_id=row['task_id'];world=AppWorld(task_id=task_id,experiment_name=f'typed_live_{task_number}',ground_truth_mode='full',load_ground_truth=True,raise_on_failure=False,raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True);code=world.task.ground_truth.compiled_solution_code+'\nsolution(apis, requester)'
  try:
   with LiveTraceRecorder(world,f'typed_{task_number}') as recorder:message=world.execute(code)
   tracker=world.evaluate();baseline='Execution failed' not in message and tracker.success;calls=recorder.calls;calls_by_task[task_id]=calls;resolver=TraceResolver();mutations=[]
   for call in calls:
    if call.checkpoint_id is None:continue
    doc=next(x for x in resolver.docs_for(call.app_name) if x['api_name']==call.api_name);pdocs={x['name']:x for x in doc.get('parameters',[])};resolved=ResolvedCall(call.index,call.method,call.app_name,call.api_name,canonical(call.arguments),canonical(pdocs));history_by_site[(task_id,call.index)]=[{'call_index':x.index,'app_name':x.app_name,'api_name':x.api_name,'method':x.method,'arguments':x.arguments,'response':x.response} for x in calls[:call.index]]
    for mutation in mutations_for(resolved,4):mutations.append(mutation);mutations_by_id[(task_id,mutation.mutation_id)]=mutation
   mutations=sorted(mutations,key=lambda x:x.mutation_id)[:c['max_mutations_per_task']]
   if baseline:
    for mutation in mutations:
     target=calls[mutation.call_index];world.load_state(target.checkpoint_id);action=True;suffix=True
     try:world.requester.request(target.app_name,target.api_name,raise_on_failure=True,**mutation.arguments())
     except Exception:action=False
     if action:
      for future in calls[target.index+1:]:
       try:world.requester.request(future.app_name,future.api_name,raise_on_failure=True,**future.arguments)
       except Exception:suffix=False;break
     final=False
     if action and suffix:world._save_state(world.output_db_home_path_on_disk);final=world.evaluate().success
     if action and suffix and not final:strict.append({'task_id':task_id,'task_type':row['task_type'],'call_index':mutation.call_index,'mutation_id':mutation.mutation_id})
  finally:AppWorld.close_all()
  task_summaries.append({'task_id':task_id,'task_type':row['task_type'],'baseline_pass':baseline,'live_calls':len(calls),'write_checkpoints':sum(x.checkpoint_id is not None for x in calls),'candidate_mutations':len(mutations)})
 sites={}
 for row in strict:
  key=(row['task_type'],row['call_index'])
  if key not in sites or row['mutation_id']<sites[key]['mutation_id']:sites[key]=row
 by_type=collections.defaultdict(list)
 for row in sites.values():by_type[row['task_type']].append(row)
 selected=[]
 for task_type,z in sorted(by_type.items()):selected+=sorted(z,key=lambda x:S(f"{x['task_type']}|{x['call_index']}|{x['mutation_id']}"))[:c['max_pairs_per_task_type']]
 results=[];cfg={'max_citations_per_field_candidate':3,'max_dict_items':8,'max_list_items':3,'max_string_chars':120}
 for row in sorted(selected,key=lambda x:S(f"{x['task_type']}|{x['call_index']}|{x['mutation_id']}")):
  target=calls_by_task[row['task_id']][row['call_index']];live=target.arguments;dead=mutations_by_id[(row['task_id'],row['mutation_id'])].arguments();fields=sorted(k for k in set(live)|set(dead) if live.get(k)!=dead.get(k));history=history_by_site[(row['task_id'],row['call_index'])];goal=json.loads((root/'data'/'tasks'/row['task_id']/'specs.json').read_text())['instruction'];old_live=candidate_evidence(live,fields,history,goal,cfg,3);old_dead=candidate_evidence(dead,fields,history,goal,cfg,3);typed_live=candidate_typed_evidence(live,dead,history,goal);typed_dead=candidate_typed_evidence(dead,live,history,goal);pair=S(f"typed|{row['task_type']}|{row['call_index']}|{row['mutation_id']}");live_a=int(pair,16)%2==0;old_a,old_b=(old_live,old_dead) if live_a else (old_dead,old_live);typed_a,typed_b=(typed_live,typed_dead) if live_a else (typed_dead,typed_live);preferred='A' if live_a else 'B';old_choice=deterministic_choice(old_a,old_b);new_choice=typed_choice(typed_a,typed_b);results.append({'pair_id':pair,'task_id':row['task_id'],'task_type':row['task_type'],'preferred':preferred,'old_choice':old_choice,'old_covered':old_choice is not None,'old_correct':old_choice==preferred if old_choice else None,'old_support_A':old_a['support_count'],'old_support_B':old_b['support_count'],'typed_choice':new_choice,'typed_covered':new_choice is not None,'typed_correct':new_choice==preferred if new_choice else None,'typed_tier_A':typed_a['max_tier'],'typed_tier_B':typed_b['max_tier']})
 def metrics(prefix):
  covered=[x for x in results if x[f'{prefix}_covered']];correct=sum(bool(x[f'{prefix}_correct']) for x in covered);return {'coverage':len(covered)/len(results) if results else 0,'covered':len(covered),'correct':correct,'wrong':len(covered)-correct,'accuracy':correct/len(covered) if covered else 0}
 old=metrics('old');typed=metrics('typed');t0=all(x['baseline_pass'] for x in task_summaries);t1=len(results)>=10 and len({x['task_type'] for x in results})>=5;t2=typed['coverage']>=.50;t3=typed['accuracy']>=.80 and typed['wrong']==0;t4=typed['wrong']<=old['wrong'];forbidden={'evidence','instruction','arguments','response','solution','evaluation'};t5=all(not (set(x)&forbidden) for x in results);gates={'T0_live_trace':t0,'T1_yield':t1,'T2_typed_coverage':t2,'T3_typed_safety':t3,'T4_vs_old_safety':t4,'T5_scope':t5}
 if not t0 or not t5:status=c['verdicts']['protocol']
 elif all(gates.values()):status=c['verdicts']['go']
 else:status=c['verdicts']['no_go']
 payload={'schema':'recurrent_appworld_typed_provenance_development_v1','status':status,'gates':gates,'source_task_types':len(selected_tasks),'strict_pairs':len(results),'strict_task_types':len({x['task_type'] for x in results}),'old_guard':old,'typed_guard':typed,'task_summaries':task_summaries,'rows':results,'reserved_train_variations':True,'independent_task_type_confirmation':False,'model_gpu_docker_used':False,'headline_eligible':False};out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);(out/'results.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# AppWorld Typed Provenance — Reserved Variation Development','',f"## Verdict: **`{status}`**",'',f"- Strict pairs: {len(results)}",f"- Task types: {payload['strict_task_types']}/{len(selected_tasks)}",'','| Guard | Coverage | Covered accuracy | Wrong choices |','|---|---:|---:|---:|',f"| Old citation count | {old['coverage']:.3f} | {old['accuracy']:.3f} | {old['wrong']} |",f"| Typed max-tier | {typed['coverage']:.3f} | {typed['accuracy']:.3f} | {typed['wrong']} |",'','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','This uses reserved variations of exposed train task types. It is development evidence, not independent task-type confirmation.'];(out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'pairs':len(results),'old':old,'typed':typed,'report':str((out/'REPORT.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
