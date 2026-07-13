"""Build train-only comparative AppWorld prompts with symmetric provenance evidence."""
from __future__ import annotations
import argparse,collections,hashlib,json,warnings
from pathlib import Path
from experiments.appworld_provenance import candidate_evidence,deterministic_choice
from experiments.appworld_trace_replay import TraceResolver,canonical,execute_call
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def S(x):return hashlib.sha256(x.encode()).hexdigest()
def prompt(arm,shared,a,b,evidence_a=None,evidence_b=None):
 payload={**shared,'candidate_A_arguments':a,'candidate_B_arguments':b}
 if arm=='C2_comparative_provenance':payload.update({'candidate_A_provenance':evidence_a,'candidate_B_provenance':evidence_b})
 return '\n'.join(['Recurrent app-specialist comparative pre-commit verifier. Return JSON only.','Choose which candidate API call better satisfies the task goal and committed evidence.','Judge the concrete arguments, not whether the API category is generally risky.','Schema: {"preferred_candidate":"A" or "B", "confidence": number between 0 and 1}','Confidence is the probability that the chosen candidate is better.',canonical(payload)])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_comparative_development_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_comparative_development'));a=ap.parse_args();warnings.filterwarnings('ignore');cp=R(a.contract);c=json.loads(cp.read_text());sourcep=R(c['source_manifest']);labelp=R(c['source_labels']);failurep=R(c['source_failure_analysis']);source=json.loads(sourcep.read_text())['rows'];labels={x['sample_id']:x for x in json.loads(labelp.read_text())['rows']};failure=json.loads(failurep.read_text())
 if c['status']!='FROZEN_BEFORE_COMPARATIVE_MODEL_OUTCOMES' or failure['status']!='RPD_APPWORLD_A3_SIGNAL_MODEL_FAIL':raise ValueError('A4 source not frozen negative')
 pairs=collections.defaultdict(list)
 for row in source:pairs[row['pair_id']].append(row)
 pair_data=[]
 for pair_id,items in pairs.items():
  live=next(x for x in items if not labels[x['sample_id']]['label']);dead=next(x for x in items if labels[x['sample_id']]['label']);lp=json.loads(live['prompt'].splitlines()[-1]);dp=json.loads(dead['prompt'].splitlines()[-1]);pair_data.append({'pair_id':pair_id,'task_id':live['task_id'],'task_type':live['task_type'],'call_index':labels[dead['sample_id']]['call_index'],'live':lp,'dead':dp})
 root=R(c['appworld_root']);from appworld import AppWorld,update_root
 update_root(str(root));by_task=collections.defaultdict(list)
 for row in pair_data:by_task[row['task_id']].append(row)
 histories={}
 for task_number,(task_id,task_pairs) in enumerate(sorted(by_task.items())):
  raw=json.loads((root/'data'/'tasks'/task_id/'ground_truth'/'api_calls.json').read_text());calls=TraceResolver().resolve_all(raw);wanted={x['call_index'] for x in task_pairs};history=[];world=AppWorld(task_id=task_id,experiment_name=f'a4_provenance_{task_number}',load_ground_truth=True,ground_truth_mode='minimal',raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True)
  try:
   for call in calls:
    if call.index in wanted:histories[(task_id,call.index)]=list(history)
    response=execute_call(world,call);history.append({'call_index':call.index,'app_name':call.app_name,'api_name':call.api_name,'method':call.method,'arguments':call.arguments(),'response':response})
  finally:AppWorld.close_all()
 prompts=[];label_rows=[];det_rows=[];cfg=c['provenance']
 for row in sorted(pair_data,key=lambda x:x['pair_id']):
  lp,dp=row['live'],row['dead'];live_args=lp['candidate_arguments'];dead_args=dp['candidate_arguments'];differing=sorted(k for k in set(live_args)|set(dead_args) if live_args.get(k)!=dead_args.get(k));history=histories[(row['task_id'],row['call_index'])];live_evidence=candidate_evidence(live_args,differing,history,lp['task_goal'],cfg,cfg['max_citations_per_field_candidate']);dead_evidence=candidate_evidence(dead_args,differing,history,lp['task_goal'],cfg,cfg['max_citations_per_field_candidate']);live_is_a=int(row['pair_id'],16)%2==0;base={'A':live_args if live_is_a else dead_args,'B':dead_args if live_is_a else live_args};base_evidence={'A':live_evidence if live_is_a else dead_evidence,'B':dead_evidence if live_is_a else live_evidence};preferred='A' if live_is_a else 'B';choice=deterministic_choice(base_evidence['A'],base_evidence['B']);det_rows.append({'pair_id':row['pair_id'],'task_type':row['task_type'],'support_A':base_evidence['A']['support_count'],'support_B':base_evidence['B']['support_count'],'preferred':preferred,'choice':choice,'covered':choice is not None,'correct':choice==preferred if choice else None})
  shared={'task_goal':lp['task_goal'],'recent_committed_evidence':lp['recent_committed_evidence'],'candidate_specialist_app':lp['candidate_specialist_app'],'candidate_api':lp['candidate_api'],'candidate_method':lp['candidate_method'],'api_purpose':lp['api_purpose'],'visible_parameter_schema':lp['visible_parameter_schema']}
  for arm in c['arms']:
   for order in c['orders']:
    if order=='AB':a_args,b_args=base['A'],base['B'];ea,eb=base_evidence['A'],base_evidence['B'];answer=preferred
    else:a_args,b_args=base['B'],base['A'];ea,eb=base_evidence['B'],base_evidence['A'];answer='B' if preferred=='A' else 'A'
    text=prompt(arm,shared,a_args,b_args,ea,eb);sample_id=S(f"{row['pair_id']}|{arm}|{order}");prompts.append({'sample_id':sample_id,'pair_id':row['pair_id'],'task_type':row['task_type'],'arm':arm,'order':order,'prompt':text,'prompt_sha256':S(text)});label_rows.append({'sample_id':sample_id,'pair_id':row['pair_id'],'task_type':row['task_type'],'arm':arm,'order':order,'preferred_candidate':answer})
 prompts.sort(key=lambda x:x['prompt_sha256']);label_rows.sort(key=lambda x:x['sample_id']);covered=[x for x in det_rows if x['covered']];det={'coverage':len(covered)/len(det_rows),'covered_accuracy':sum(x['correct'] for x in covered)/len(covered) if covered else None,'overall_correct_or_abstain':sum(bool(x['correct']) for x in covered)/len(det_rows),'rows':det_rows};checks={'pairs':len(pairs)==c['expected_pairs'],'prompts':len(prompts)==c['expected_prompts'],'unique':len({x['prompt_sha256'] for x in prompts})==len(prompts),'arm_counts':all(sum(x['arm']==arm for x in prompts)==30 for arm in c['arms']),'order_counts':all(sum(x['order']==order for x in prompts)==30 for order in c['orders']),'exact_label_ids':{x['sample_id'] for x in prompts}=={x['sample_id'] for x in label_rows},'no_labels_in_prompts':all('preferred_candidate' not in x for x in prompts)};out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);mp=out/'prompt_manifest.json';lpout=out/'adjudication_manifest.json';mp.write_text(json.dumps({'schema':'recurrent_appworld_a4_comparative_prompt_manifest_v1','status':'FROZEN_BEFORE_MODEL_OUTCOMES','model':c['model'],'model_revision':c['model_revision'],'protected_local_only':True,'rows':prompts},indent=2,sort_keys=True)+'\n');lpout.write_text(json.dumps({'schema':'recurrent_appworld_a4_comparative_adjudication_v1','status':'FROZEN_BLINDED_LABELS','rows':label_rows},indent=2,sort_keys=True)+'\n');payload={'schema':'recurrent_appworld_a4_manifest_v1','status':'APPWORLD_A4_MANIFEST_COMPLETE','checks':checks,'pairs':len(pairs),'prompts':len(prompts),'deterministic_provenance':det,'hashes':{'contract':H(cp),'source_manifest':H(sourcep),'source_labels':H(labelp),'source_failure':H(failurep),'provenance_source':H(REPO_ROOT/'experiments/appworld_provenance.py'),'trace_source':H(REPO_ROOT/'experiments/appworld_trace_replay.py'),'source':H(Path(__file__)),'prompt_manifest':H(mp),'adjudication_manifest':H(lpout)},'model_outcomes_observed':False,'train_only':True,'headline_eligible':False};(out/'manifest.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':payload['status'],'prompts':len(prompts),'deterministic':{k:v for k,v in det.items() if k!='rows'}}))
if __name__=='__main__':main()
