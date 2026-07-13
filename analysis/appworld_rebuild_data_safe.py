"""Safely rebuild AppWorld data without the upstream all.py process-killing side effects."""
from __future__ import annotations
import argparse,json,os,subprocess,time
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
APPS=('api_docs','admin','file_system','gmail','phone','amazon','simple_note','spotify','venmo','splitwise','todoist')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--source-root',type=Path,default=Path('external_repos/appworld_source'));ap.add_argument('--appworld-root',type=Path,default=Path('external_repos/appworld_generated'));ap.add_argument('--output-dir',type=Path,default=Path('results/appworld_data_v02_rebuild'));ap.add_argument('--resume',action='store_true');a=ap.parse_args();source=(a.source_root if a.source_root.is_absolute() else REPO_ROOT/a.source_root).resolve();root=(a.appworld_root if a.appworld_root.is_absolute() else REPO_ROOT/a.appworld_root).resolve();out=(a.output_dir if a.output_dir.is_absolute() else REPO_ROOT/a.output_dir).resolve()
 if REPO_ROOT not in root.parents or 'appworld_generated' not in str(root):raise ValueError('refusing to write outside isolated generated root')
 python=source/'.venv/bin/python';statusp=out/'status.json';completed=[]
 if a.resume and statusp.exists():completed=json.loads(statusp.read_text()).get('completed_apps',[])
 out.mkdir(parents=True,exist_ok=True);env=os.environ.copy();env.update({'APPWORLD_ROOT':str(root),'PYTHONPATH':str(source),'PYTHONHASHSEED':'0','PYTHONWARNINGS':'ignore'});started=time.time();rows=[]
 for app in APPS:
  if app in completed:continue
  command=[str(python),'-u',str(source/'generate/data'/f'{app}.py')]
  if app=='api_docs':command.append('--delete_db_collection')
  logp=out/f'{app}.log';t0=time.time();print(json.dumps({'starting_app':app,'log':str(logp.relative_to(REPO_ROOT))}),flush=True)
  with logp.open('w') as log:process=subprocess.run(command,cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,check=False)
  row={'app':app,'returncode':process.returncode,'seconds':time.time()-t0,'log_sha256':__import__('hashlib').sha256(logp.read_bytes()).hexdigest()};rows.append(row)
  if process.returncode!=0:
   payload={'schema':'appworld_data_v02_safe_rebuild_v1','status':'APPWORLD_DATA_V02_REBUILD_FAIL','completed_apps':completed,'failed_app':app,'rows':rows,'external_process_actions':False};statusp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':payload['status'],'failed_app':app}));raise SystemExit(process.returncode)
  completed.append(app);statusp.write_text(json.dumps({'schema':'appworld_data_v02_safe_rebuild_v1','status':'IN_PROGRESS','completed_apps':completed,'rows':rows,'external_process_actions':False},indent=2,sort_keys=True)+'\n');print(json.dumps({'finished_app':app,'seconds':round(row['seconds'],1)}),flush=True)
 (root/'data/version.txt').write_text('0.2.0\n');payload={'schema':'appworld_data_v02_safe_rebuild_v1','status':'APPWORLD_DATA_V02_REBUILD_PASS','completed_apps':completed,'rows':rows,'total_seconds':time.time()-started,'data_version':'0.2.0','external_process_actions':False,'system_packages_installed':False};statusp.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');lines=['# AppWorld Data 0.2 Safe Rebuild','',f"## Status: **`{payload['status']}`**",'',f"- Completed apps: {len(completed)}/{len(APPS)}",f"- Total time: {payload['total_seconds']/60:.1f} minutes",'- External process actions: No','- System package installation: No'];(out/'REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'status':payload['status'],'minutes':round(payload['total_seconds']/60,1),'report':str((out/'REPORT.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
