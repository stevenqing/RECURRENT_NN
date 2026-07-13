"""Train-only yield census for successful-but-harmful AppWorld write mutations."""
from __future__ import annotations
import argparse,collections,json,warnings
from pathlib import Path
from experiments.appworld_trace_replay import TraceResolver,execute_call,mutations_for
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--appworld-root',type=Path,default=Path('external_repos/appworld_runtime'));ap.add_argument('--public-manifest',type=Path,default=Path('results/recurrent_parallel_appworld_preflight_v2/candidate_manifest.json'));ap.add_argument('--adjudication-manifest',type=Path,default=Path('results/recurrent_parallel_appworld_preflight_v2/adjudication_manifest.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_semantic_mutation_development'));ap.add_argument('--max-mutations-per-task',type=int,default=24);a=ap.parse_args();warnings.filterwarnings('ignore');root=R(a.appworld_root);public=json.loads(R(a.public_manifest).read_text())['rows'];protected=json.loads(R(a.adjudication_manifest).read_text())['rows'];keys={x['task_id']:x['selection_key'] for x in public};train=[{**x,'selection_key':keys[x['task_id']]} for x in protected if x['split']=='train'];groups={}
 for row in train:groups.setdefault(row['task_type'],[]).append(row)
 selected=[min(rows,key=lambda x:x['selection_key']) for _,rows in sorted(groups.items())]
 from appworld import AppWorld,update_root
 update_root(str(root));all_rows=[];task_rows=[]
 for task_number,row in enumerate(selected):
  task_id=row['task_id'];raw=json.loads((root/'data'/'tasks'/task_id/'ground_truth'/'api_calls.json').read_text());calls=TraceResolver().resolve_all(raw);mutations=[]
  for call in calls:
   if call.method=='get' or call.app_name in {'supervisor','api_docs'} or any(x in call.api_name.lower() for x in ('login','auth','token')):continue
   mutations.extend(mutations_for(call,4))
  mutations=sorted(mutations,key=lambda x:x.mutation_id)[:a.max_mutations_per_task];by_index=collections.defaultdict(list)
  for mutation in mutations:by_index[mutation.call_index].append(mutation)
  world=AppWorld(task_id=task_id,experiment_name=f'a3_mutation_dev_{task_number}',load_ground_truth=True,ground_truth_mode='minimal',raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True);baseline_ok=True
  try:
   for call in calls:
    if call.index in by_index:world.save_state(f'before_{call.index}')
    try:execute_call(world,call)
    except Exception:baseline_ok=False;break
   if baseline_ok:
    world._save_state(world.output_db_home_path_on_disk);baseline_ok=world.evaluate().success
   for mutation in mutations:
    world.load_state(f'before_{mutation.call_index}');action_succeeded=True;suffix_succeeded=True
    try:execute_call(world,calls[mutation.call_index],mutation.arguments())
    except Exception:action_succeeded=False
    if action_succeeded:
     for call in calls[mutation.call_index+1:]:
      try:execute_call(world,call)
      except Exception:suffix_succeeded=False;break
    final_pass=False
    if action_succeeded and suffix_succeeded:
     world._save_state(world.output_db_home_path_on_disk);final_pass=world.evaluate().success
    outcome='action_fail' if not action_succeeded else ('semantic_live' if final_pass else 'semantic_dead');all_rows.append({'task_id':task_id,'task_type':row['task_type'],'required_app_count':row['required_app_count'],'call_index':mutation.call_index,'mutation_id':mutation.mutation_id,'mutation_kind':mutation.mutation_kind,'action_succeeded':action_succeeded,'suffix_succeeded':suffix_succeeded,'final_pass':final_pass,'outcome':outcome})
  finally:AppWorld.close_all()
  subset=[x for x in all_rows if x['task_id']==task_id];task_rows.append({'task_id':task_id,'task_type':row['task_type'],'required_app_count':row['required_app_count'],'baseline_pass':baseline_ok,'mutations':len(subset),'action_fail':sum(x['outcome']=='action_fail' for x in subset),'semantic_live':sum(x['outcome']=='semantic_live' for x in subset),'semantic_dead':sum(x['outcome']=='semantic_dead' for x in subset)})
 counts=collections.Counter(x['outcome'] for x in all_rows);kind_dead=collections.Counter(x['mutation_kind'] for x in all_rows if x['outcome']=='semantic_dead');payload={'schema':'recurrent_appworld_semantic_mutation_development_v1','status':'APPWORLD_A3_MUTATION_YIELD_MEASURED','tasks':len(task_rows),'all_baselines_pass':all(x['baseline_pass'] for x in task_rows),'mutation_counts':dict(counts),'semantic_dead_task_types':len({x['task_type'] for x in all_rows if x['outcome']=='semantic_dead'}),'semantic_dead_call_sites':len({(x['task_type'],x['call_index']) for x in all_rows if x['outcome']=='semantic_dead'}),'semantic_dead_by_kind':dict(kind_dead),'task_summary':task_rows,'rows':all_rows,'prompt_manifest_generated':False,'dev_or_test_read':False,'model_gpu_docker_used':False,'headline_eligible':False};out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);(out/'results.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# AppWorld A3 Semantic-Mutation Yield Development','',f"## Status: **`{payload['status']}`**",'',f"- Independent train task types: {payload['tasks']}",f"- All baseline traces pass: {payload['all_baselines_pass']}",f"- Candidate mutations: {len(all_rows)}",f"- Action failures discarded: {counts['action_fail']}",f"- Semantically live mutations: {counts['semantic_live']}",f"- Semantically dead successful writes: {counts['semantic_dead']}",f"- Dead-bearing task types: {payload['semantic_dead_task_types']}",f"- Distinct dead call sites: {payload['semantic_dead_call_sites']}",'- Prompt/model outcomes: None','- Dev/test read: No','','Only successful mutations that fail under the unchanged official continuation are eligible correction examples. This is a train-only yield census, not a signal or performance result.'];(out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':payload['status'],'counts':dict(counts),'dead_types':payload['semantic_dead_task_types'],'report':str((out/'REPORT.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
