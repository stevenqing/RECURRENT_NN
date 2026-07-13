"""Pre-outcome lock for AppWorld fresh-task generation v2 PATH repair."""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tree_hash(path):
 h=hashlib.sha256()
 for item in sorted(x for x in path.rglob('*') if x.is_file()):h.update(str(item.relative_to(path)).encode());h.update(hashlib.sha256(item.read_bytes()).digest())
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_generated_tasks_v2.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_generated_tasks_v2'));a=ap.parse_args();cp=R(a.contract);c=json.loads(cp.read_text());failure=json.loads(R(c['v1_failure']).read_text());source=R(c['source_root']);root=R(c['generated_root']);rebuildp=R(c['base_rebuild_status']);rebuild=json.loads(rebuildp.read_text());out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);commit=subprocess.run(['git','rev-parse','HEAD'],cwd=source,capture_output=True,text=True,check=True).stdout.strip();files=['specs/recurrent_parallel_appworld_generated_tasks_v2.md','specs/recurrent_parallel_appworld_generated_tasks_v2.json','analysis/appworld_generated_tasks_v2_preflight.py','analysis/appworld_generate_tasks_safe_v2.py',c['v1_contract'],c['v1_failure'],c['base_rebuild_status']];checks={'contract_frozen':c['status']=='FROZEN_BEFORE_COMPLETE_GENERATED_TASK_OUTCOMES','v1_failure_preserved':failure['status']=='RPD_APPWORLD_GENERATED_TASKS_FAIL' and failure['validation_outcomes_observed']==0,'source_commit':commit==c['source_commit'],'base_rebuild':rebuild['status']=='APPWORLD_DATA_V02_REBUILD_PASS','data_version':(root/'data/version.txt').read_text().strip()==c['data_version'],'ruff_available':(source/'.venv/bin/ruff').is_file(),'files_exist':all(R(p).exists() for p in files),'outcomes_absent':not (out/'generation.json').exists()}
 if not all(checks.values()):raise RuntimeError(checks)
 lock={'schema':'recurrent_appworld_generated_tasks_v2_execution_lock','status':'LOCKED_BEFORE_COMPLETE_GENERATED_TASK_OUTCOMES','files':{p:H(R(p)) for p in files},'contract_sha256':H(cp),'source_commit':commit,'generator_tree_sha256':tree_hash(source/'generate/tasks/task_generators'),'base_dbs_tree_sha256':tree_hash(root/'data/base_dbs')};lp=out/'execution_lock.json';lp.write_text(json.dumps(lock,indent=2,sort_keys=True)+'\n');payload={'schema':'recurrent_appworld_generated_tasks_v2_preflight','status':'RPD_APPWORLD_GENERATED_TASKS_V2_EXECUTION_READY','checks':checks,'execution_lock_sha256':H(lp),'complete_task_outcomes_observed':False};(out/'preflight.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');(out/'PREFLIGHT.md').write_text('\n'.join(['# AppWorld Fresh Task Generation v2 Preflight','',f"## Status: **`{payload['status']}`**",'']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in checks.items()])+'\n');print(json.dumps({'status':payload['status'],'lock':str(lp.relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
