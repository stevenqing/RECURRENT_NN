"""Pre-outcome execution lock for untouched-dev AppWorld provenance confirmation."""
from __future__ import annotations
import argparse,json
from pathlib import Path
REPO_ROOT=Path(__file__).resolve().parents[1]
def R(p):
 p=Path(p);return p if p.is_absolute() else REPO_ROOT/p
def H(p):
 import hashlib
 return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_appworld_provenance_confirmation_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_appworld_provenance_confirmation'));a=ap.parse_args();cp=R(a.contract);c=json.loads(cp.read_text());dev=json.loads(R(c['development_result']).read_text());out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);files=['specs/recurrent_parallel_appworld_provenance_confirmation_v1.md','specs/recurrent_parallel_appworld_provenance_confirmation_v1.json','experiments/appworld_provenance.py','experiments/appworld_trace_replay.py','analysis/recurrent_appworld_provenance_confirmation_preflight.py','analysis/recurrent_appworld_provenance_confirmation.py',c['development_result'],c['candidate_manifest'],c['adjudication_manifest']];checks={'contract_frozen':c['status']=='FROZEN_BEFORE_DEV_MUTATION_OUTCOMES','development_go':dev['status']=='RPD_APPWORLD_A4_DETERMINISTIC_PROVENANCE_GO','source_types':c['expected_source_task_types']==7,'files_exist':all(R(p).exists() for p in files),'results_absent':not (out/'results.json').exists()}
 if not all(checks.values()):raise RuntimeError(checks)
 lock={'schema':'recurrent_appworld_a5_execution_lock_v1','status':'LOCKED_BEFORE_DEV_OUTCOMES','files':{p:H(R(p)) for p in files},'contract_sha256':H(cp),'split':c['split'],'expected_source_task_types':c['expected_source_task_types']};lp=out/'execution_lock.json';lp.write_text(json.dumps(lock,indent=2,sort_keys=True)+'\n');payload={'schema':'recurrent_appworld_a5_preflight_v1','status':'RPD_APPWORLD_A5_EXECUTION_READY','checks':checks,'execution_lock_sha256':H(lp),'dev_outcomes_observed':False};(out/'preflight.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');(out/'PREFLIGHT.md').write_text('\n'.join(['# AppWorld A5 — Provenance Confirmation Preflight','',f"## Status: **`{payload['status']}`**",'']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in checks.items()])+'\n');print(json.dumps({'status':payload['status'],'lock':str(lp.relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
