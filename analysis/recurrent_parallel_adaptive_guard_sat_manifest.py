"""Generate zero-overlap SAT manifest for adaptive recurrent guard confirmation."""
from __future__ import annotations
import argparse, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.signal.long_diameter_sat import clause_hash, generate_long_diameter_sat, initial_parent_child_mismatches, local_pair_extendability, public_instance, verify_sat

SCHEMA="recurrent_parallel_adaptive_guard_sat_confirmation_contract_v1"
STATUS="RPD_ADAPTIVE_SAT_MANIFEST_FROZEN"
def _r(p:str|Path)->Path:
 v=Path(p); return v if v.is_absolute() else REPO_ROOT/v
def _h(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->None:
 ap=argparse.ArgumentParser(); ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_adaptive_guard_sat_confirmation_v1.json')); ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_adaptive_guard_sat_manifest')); a=ap.parse_args()
 cp=_r(a.contract); c=json.loads(cp.read_text());
 if c.get('schema')!=SCHEMA or c.get('status')!='FROZEN_BEFORE_MANIFEST_AND_OUTCOMES': raise ValueError('adaptive SAT confirmation contract not frozen')
 dev_gate_path=_r(c['development_gate']); dev_gate=json.loads(dev_gate_path.read_text());
 if dev_gate.get('status')!='RPD_ADAPTIVE_GUARD_SAT_DEV_GO_CONFIRMATION' or not dev_gate.get('independent_confirmation_authorized'): raise ValueError('adaptive SAT confirmation blocked')
 dev_path=_r(c['development_manifest']); dev=list(json.loads(dev_path.read_text())['rows']); old_ids={x['instance_id'] for x in dev}; old_hashes={x['clause_sha256'] for x in dev}
 cfg=c['manifest']; rows=[]; audit_rows=[]
 for d in map(int,cfg['diameters']):
  for i in range(int(cfg['instances_per_diameter'])):
   full=generate_long_diameter_sat(base_seed=int(cfg['base_seed']),candidate_index=i,diameter=d,split=str(cfg['split']))
   planted={int(k):int(v) for k,v in full['planted_assignment'].items()}; public=public_instance(full); public['clause_sha256']=clause_hash(public); ext=all(local_pair_extendability(public).values()); mismatch=initial_parent_child_mismatches(public)
   rows.append(public); audit_rows.append({'id':public['instance_id'],'diameter':d,'planted_valid':verify_sat(full,planted),'extendable':ext,'mismatches':mismatch})
 ids={x['instance_id'] for x in rows}; hashes={x['clause_sha256'] for x in rows}; counts=Counter(x['partition_diameter'] for x in rows)
 checks={'complete':len(rows)==200 and all(counts[d]==50 for d in map(int,cfg['diameters'])),'unique_ids':len(ids)==200,'unique_hashes':len(hashes)==200,'zero_dev_id_overlap':not bool(ids&old_ids),'zero_dev_hash_overlap':not bool(hashes&old_hashes),'fixed_clauses':len({(x['n_clauses'],x['n_local_clauses'],x['n_cross_clauses']) for x in rows})==1,'planted_valid':all(x['planted_valid'] for x in audit_rows),'planted_removed':all('planted_assignment' not in x for x in rows),'extendable':all(x['extendable'] for x in audit_rows),'engaged':all(x['mismatches']>=8 for x in audit_rows)}
 if not all(checks.values()): raise RuntimeError(checks)
 out=_r(a.output_dir); out.mkdir(parents=True,exist_ok=True); mp=out/'instance_manifest.json'; mp.write_text(json.dumps({'schema':'recurrent_parallel_adaptive_sat_manifest_v1','status':STATUS,'rows':rows},indent=2,sort_keys=True)+'\n')
 hashes_out={'manifest':_h(mp),'contract_json':_h(cp),'contract_md':_h(REPO_ROOT/'specs/recurrent_parallel_adaptive_guard_sat_confirmation_v1.md'),'development_gate':_h(dev_gate_path),'development_manifest':_h(dev_path),'generator':_h(REPO_ROOT/'experiments/signal/long_diameter_sat.py'),'engine':_h(REPO_ROOT/'experiments/recurrent_parallel_sat_core.py'),'source':_h(Path(__file__))}
 payload={'schema':'recurrent_parallel_adaptive_sat_generation_v1','status':STATUS,'checks':checks,'counts':dict(counts),'overlap':{'ids':len(ids&old_ids),'hashes':len(hashes&old_hashes)},'mismatch_range':[min(x['mismatches'] for x in audit_rows),max(x['mismatches'] for x in audit_rows)],'hashes':hashes_out}; (out/'generation.json').write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
 md=['# Adaptive SAT Confirmation Manifest','',f"## Status: **`{STATUS}`**",'',f"- Instances: {len(rows)} (50/diameter)",'- Policy outcomes generated/read: **No**','- GPU/LLM use: none','','## Audit','']+[f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in checks.items()]+['',f"- Development overlap IDs/hashes: `{payload['overlap']['ids']}/{payload['overlap']['hashes']}`",f"- Initial mismatch range: `{payload['mismatch_range']}`",'', '## Hashes','']+[f"- `{k}`: `{v}`" for k,v in hashes_out.items()]
 (out/'GENERATION.md').write_text('\n'.join(md)+'\n'); print(json.dumps({'status':STATUS,'instances':len(rows),'manifest_sha256':hashes_out['manifest'],'report':str((out/'GENERATION.md').relative_to(REPO_ROOT))}))
if __name__=='__main__':main()
