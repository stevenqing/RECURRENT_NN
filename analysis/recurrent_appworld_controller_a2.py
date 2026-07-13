"""A2 integrity audit for recurrent parallel specialists on real AppWorld state."""
from __future__ import annotations
import argparse,copy,hashlib,json
from pathlib import Path
from typing import Any
from experiments.recurrent_appworld_controller import RecurrentBarrierController,RoundSnapshot,ToolProposal,canonical,digest
REPO_ROOT=Path(__file__).resolve().parents[1]
SCHEMA='recurrent_parallel_appworld_controller_contract_v1'
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def proposal(pid,agent,phase,app,api,args=None,targets=()):return ToolProposal(pid,agent,phase,app,api,canonical(args or {}),tuple(targets))
class FakeAdapter:
 def __init__(self):self.state={'counter':0};self.saved={};self.loads=[]
 def save_state(self,state_id):self.saved[state_id]=copy.deepcopy(self.state)
 def load_state(self,state_id):self.state=copy.deepcopy(self.saved[state_id]);self.loads.append(state_id)
 def state_digest(self):return digest(self.state)
 def execute(self,p):
  if p.api_name=='fail':raise RuntimeError('frozen fake failure')
  if p.phase=='write':self.state['counter']+=int(p.arguments().get('delta',1))
  return {'proposal_id':p.proposal_id,'counter':self.state['counter']}
def fake_run(prefix):
 adapter=FakeAdapter();controller=RecurrentBarrierController(adapter,prefix);immutable=[]
 def fn(agent,items):
  def inner(snapshot):
   try:setattr(snapshot,'round_index',999);immutable.append(False)
   except Exception:immutable.append(True)
   return items(snapshot)
  return inner
 controller.run_round({'a':fn('a',lambda s:[proposal('a_read0','a','read','fake','read',targets=('b',))]),'b':fn('b',lambda s:[proposal('b_read0','b','read','fake','read',targets=('a',))])})
 controller.run_round({'a':fn('a',lambda s:[proposal('a_read1','a','read','fake','read',targets=('b',))]),'b':fn('b',lambda s:[proposal('b_write1','b','write','fake','add',{'delta':1},('a',))])})
 before=copy.deepcopy(adapter.state);controller.run_round({'a':fn('a',lambda s:[proposal('a_read2','a','read','fake','read')]),'b':fn('b',lambda s:[proposal('b_fail2','b','write','fake','fail')])});return adapter,controller,immutable,before
class AppWorldAdapter:
 def __init__(self,world):self.world=world
 def save_state(self,state_id):self.world.save_state(state_id)
 def load_state(self,state_id):self.world.load_state(state_id)
 def state_digest(self):return digest(self.world.requester.request('supervisor','show_active_task',track=False))
 def execute(self,p):return self.world.requester.request(p.app_name,p.api_name,**p.arguments())
 def evaluator_digest(self):
  self.world._save_state(self.world.output_db_home_path_on_disk)
  return digest(self.world.evaluate().to_dict())
def real_schedule(controller,required_app_names):
 specialists=[f'specialist_{i}' for i in range(len(required_app_names))]
 r0={}
 for i,(agent,app) in enumerate(zip(specialists,required_app_names)):
  r0[agent]=lambda s,i=i,agent=agent,app=app:[proposal(f'docs_{i}',agent,'read','api_docs','show_api_descriptions',{'app_name':app},('coordinator',))]
 a0=controller.run_round(r0)
 def coordinator(s):
  assert len(s.for_agent('coordinator'))==len(required_app_names)
  return [proposal('mark_fail','coordinator','write','supervisor','complete_task',{'status':'fail'},tuple(specialists))]
 def observer(s):
  assert len(s.for_agent('observer'))==0
  return [proposal('status_before','observer','read','supervisor','show_active_task',targets=('coordinator',))]
 a1=controller.run_round({'coordinator':coordinator,'observer':observer});r2={}
 for i,agent in enumerate(specialists):
  def specialist(s,i=i,agent=agent):
   assert len(s.for_agent(agent))==1
   return [proposal(f'status_after_{i}',agent,'read','supervisor','show_active_task',targets=('coordinator',))]
  r2[agent]=specialist
 a2=controller.run_round(r2);return [a0,a1,a2]
def select_tasks(public_rows,protected_rows,selection):
 keys={x['task_id']:x['selection_key'] for x in public_rows};joined=[{**x,'selection_key':keys[x['task_id']]} for x in protected_rows if x['split']==selection['split']];by_count={2:{},3:{}}
 for row in joined:
  by_count[row['required_app_count']].setdefault(row['task_type'],[]).append(row)
 chosen=[]
 for task_type,rows in sorted(by_count[3].items(),key=lambda z:min(x['selection_key'] for x in z[1]))[:selection['three_app_types']]:chosen.append(min(rows,key=lambda x:x['selection_key']))
 for task_type,rows in sorted(by_count[2].items(),key=lambda z:min(x['selection_key'] for x in z[1]))[:selection['two_app_types']]:chosen.append(min(rows,key=lambda x:x['selection_key']))
 return sorted(chosen,key=lambda x:x['selection_key'])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_controller_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_controller_a2'));a=ap.parse_args();cp=R(a.contract);c=json.loads(cp.read_text());prereqp=R(c['prerequisite']);prereq=json.loads(prereqp.read_text());publicp=R(c['candidate_manifest']);protectedp=R(c['adjudication_manifest']);public=json.loads(publicp.read_text())['rows'];protected=json.loads(protectedp.read_text())['rows']
 if c.get('schema')!=SCHEMA or c.get('status')!='FROZEN_BEFORE_CONTROLLER_AND_MODEL_OUTCOMES':raise ValueError('A2 contract not frozen')
 f1,c1,immutable1,before1=fake_run('fake_a');f2,c2,immutable2,before2=fake_run('fake_b');fake_audits=c1.audits;core={'immutable':all(immutable1+immutable2),'parallel':all(x.max_proposal_concurrency==x.proposal_agent_count for x in fake_audits),'barrier':all(x.barrier_reached and x.commits_before_barrier==0 for x in fake_audits),'read_before_write':all([v.split(':',1)[0] for v in x.commit_order]==sorted([v.split(':',1)[0] for v in x.commit_order]) for x in fake_audits),'serial_write':all(x.max_write_concurrency<=1 for x in fake_audits) and any(x.max_write_concurrency==1 for x in fake_audits),'message_delay':all(age==1 for x in fake_audits[1:] for age in x.snapshot_message_ages) and all(x.same_round_message_reads==0 for x in fake_audits),'rollback':fake_audits[-1].rolled_back and f1.state==before1 and f2.state==before2,'replay':c1.normalized_transcript()==c2.normalized_transcript()}
 from appworld import AppWorld,update_root
 update_root(str(R(c['appworld_root'])));selected=select_tasks(public,protected,c['selection']);real_rows=[]
 for index,row in enumerate(selected):
  task_id=row['task_id'];apps=json.loads((R(c['appworld_root'])/'data'/'tasks'/task_id/'ground_truth'/'required_apps.json').read_text());world=AppWorld(task_id=task_id,experiment_name=f'rpd_a2_{index}',load_ground_truth=True,ground_truth_mode='minimal',raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True);adapter=AppWorldAdapter(world);initial_id=f'a2_initial_{index}';world.save_state(initial_id);initial_state=adapter.state_digest();initial_eval=adapter.evaluator_digest();ca=RecurrentBarrierController(adapter,f'real_{index}_a');audits_a=real_schedule(ca,apps);changed_a=adapter.state_digest();world.load_state(initial_id);restored_state=adapter.state_digest();restored_eval=adapter.evaluator_digest();cb=RecurrentBarrierController(adapter,f'real_{index}_b');audits_b=real_schedule(cb,apps);changed_b=adapter.state_digest();world.load_state(initial_id);final_state=adapter.state_digest();final_eval=adapter.evaluator_digest();row_out={'task_id':task_id,'task_type':row['task_type'],'variation':row['variation'],'required_app_count':len(apps),'rounds':3,'proposal_counts':[x.proposal_count for x in audits_a],'read_counts':[x.read_count for x in audits_a],'write_counts':[x.write_count for x in audits_a],'message_counts':[x.messages_generated for x in audits_a],'max_proposal_concurrency':[x.max_proposal_concurrency for x in audits_a],'max_write_concurrency':[x.max_write_concurrency for x in audits_a],'initial_state_sha256':initial_state,'changed_state_sha256':changed_a,'restored_state_sha256':restored_state,'initial_evaluator_sha256':initial_eval,'restored_evaluator_sha256':restored_eval,'normalized_transcript_sha256':digest(ca.normalized_transcript()),'checks':{'changed':changed_a!=initial_state,'restored':restored_state==initial_state==final_state,'evaluator_restored':restored_eval==initial_eval==final_eval,'replay_state':changed_b==changed_a,'replay_transcript':ca.normalized_transcript()==cb.normalized_transcript(),'messages_age_one':all(age==1 for x in audits_a[1:] for age in x.snapshot_message_ages),'read_before_write':all([v.split(':',1)[0] for v in x.commit_order]==sorted([v.split(':',1)[0] for v in x.commit_order]) for x in audits_a),'serial_write':all(x.max_write_concurrency<=1 for x in audits_a),'parallel':all(x.max_proposal_concurrency==x.proposal_agent_count for x in audits_a)}};real_rows.append(row_out);AppWorld.close_all()
 forbidden=set(c['forbidden_exports']);export_clean=all(not (set(row)&forbidden) for row in real_rows);c0=prereq.get('status')=='RPD_APPWORLD_A1_PREFLIGHT_PASS';c1gate=core['immutable'] and core['parallel'];c2gate=core['barrier'] and core['read_before_write'] and core['serial_write'];c3gate=core['message_delay'];c4gate=core['rollback'] and core['replay'];c5gate=len(real_rows)==6 and all(all(x['checks'].values()) for x in real_rows);c6gate=export_clean;gates={'C0_integrity':c0,'C1_snapshot_parallel':c1gate,'C2_barrier_serial_write':c2gate,'C3_message_delay':c3gate,'C4_rollback_replay':c4gate,'C5_real_appworld_replay':c5gate,'C6_protected_content':c6gate}
 if not c0 or not c6gate:status=c['verdicts']['protocol']
 elif all(gates.values()):status=c['verdicts']['pass']
 else:status=c['verdicts']['fail']
 out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);rawp=out/'audit_rows.json';rawp.write_text(json.dumps({'schema':'recurrent_appworld_controller_a2_rows_v1','status':status,'core':core,'rows':real_rows},indent=2,sort_keys=True)+'\n');lock_paths=['specs/recurrent_parallel_appworld_controller_v1.md','specs/recurrent_parallel_appworld_controller_v1.json','experiments/recurrent_appworld_controller.py','analysis/recurrent_appworld_controller_a2.py',c['prerequisite'],c['candidate_manifest'],c['adjudication_manifest']];lock={'schema':'recurrent_appworld_controller_a2_execution_lock_v1','status':'LOCKED_NO_MODEL_OUTCOMES','files':{p:H(R(p)) for p in lock_paths},'audit_rows_sha256':H(rawp)};lp=out/'execution_lock.json';lp.write_text(json.dumps(lock,indent=2,sort_keys=True)+'\n');payload={'schema':'recurrent_appworld_controller_a2_analysis_v1','status':status,'gates':gates,'core':core,'episodes':len(real_rows),'task_types':len({x['task_type'] for x in real_rows}),'required_app_counts':{str(k):sum(x['required_app_count']==k for x in real_rows) for k in (2,3)},'development_failures_before_artifact':['isolated runner imported reasoning_gym transitively','AppWorld load_state plus instance close double-stopped time freezer'],'hashes':{'contract':H(cp),'controller':H(REPO_ROOT/'experiments/recurrent_appworld_controller.py'),'source':H(Path(__file__)),'rows':H(rawp),'execution_lock':H(lp)},'test_task_content_inspected':False,'official_solutions_executed':False,'model_gpu_docker_used':False,'headline_eligible':False};(out/'analysis.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# AppWorld A2 — Recurrent Controller Integrity','',f"## Verdict: **`{status}`**",'',f"- Real train episodes: {len(real_rows)}",f"- Independent task types: {payload['task_types']}",f"- Required-app counts: {payload['required_app_counts']}",'- Official solutions executed: No','- Test content inspected: No','- Model/GPU/Docker used: No','','## Gates','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in gates.items()]+['','## Development plumbing failures retained','','- Initial isolated runner imported `reasoning_gym` transitively before AppWorld load.','- First real smoke completed an episode but instance cleanup double-stopped AppWorld time after `load_state`; global cleanup repaired it.','', 'A pass validates recurrent controller semantics and real AppWorld checkpoint/replay integrity. It does not show that multi-agent reasoning improves task completion.'];(out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'episodes':len(real_rows),'report':str((out/'REPORT.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
