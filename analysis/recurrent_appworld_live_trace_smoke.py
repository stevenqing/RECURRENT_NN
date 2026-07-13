"""Train-only smoke for environment-native AppWorld trace/checkpoint instrumentation."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from experiments.appworld_live_trace import LiveTraceRecorder,digest
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--appworld-root',type=Path,default=Path('external_repos/appworld_runtime'));ap.add_argument('--task-id',default='6ea6792_1');ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_live_trace_smoke'));a=ap.parse_args();root=R(a.appworld_root);from appworld import AppWorld,update_root
 update_root(str(root));world=AppWorld(task_id=a.task_id,experiment_name='live_trace_smoke',ground_truth_mode='full',load_ground_truth=True,raise_on_failure=False,raise_on_unsafe_syntax=True,null_patch_unsafe_execution=True);solution=world.task.ground_truth.compiled_solution_code+'\nsolution(apis, requester)'
 try:
  with LiveTraceRecorder(world,'smoke') as recorder:message=world.execute(solution)
  tracker=world.evaluate();writes=[x for x in recorder.calls if x.checkpoint_id is not None];replay_ok=False
  if writes:
    target=writes[0];world.load_state(target.checkpoint_id);response=world.requester.request(target.app_name,target.api_name,**target.arguments);replay_ok=digest(response)==target.response_sha256
  checks={'solution_message_no_failure':'Execution failed' not in message,'official_evaluator':tracker.success,'calls_recorded':len(recorder.calls)>0,'all_writes_checkpointed':bool(writes) and all(x.checkpoint_id for x in writes),'responses_recorded':all(x.response_sha256 for x in recorder.calls),'checkpoint_write_replay':replay_ok}
  status='RPD_APPWORLD_LIVE_TRACE_SMOKE_PASS' if all(checks.values()) else 'RPD_APPWORLD_LIVE_TRACE_SMOKE_FAIL';payload={'schema':'recurrent_appworld_live_trace_smoke_v1','status':status,'task_id':a.task_id,'calls':len(recorder.calls),'reads':sum(x.method=='get' for x in recorder.calls),'writes':len(writes),'checks':checks,'public_trace':recorder.public_summary(),'protected_arguments_responses_exported':False,'train_only':True,'model_gpu_docker_used':False};out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);(out/'results.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# AppWorld Environment-Native Live Trace Smoke','',f"## Verdict: **`{status}`**",'',f"- Live calls captured: {len(recorder.calls)}",f"- Reads: {payload['reads']}",f"- Writes/checkpoints: {len(writes)}",'- Protected arguments/responses exported: No','- Model/GPU/Docker: No','','## Checks','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in checks.items()];(out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':status,'calls':len(recorder.calls),'writes':len(writes),'report':str((out/'REPORT.md').relative_to(REPO_ROOT))}))
 finally:AppWorld.close_all()
if __name__=='__main__':main()
