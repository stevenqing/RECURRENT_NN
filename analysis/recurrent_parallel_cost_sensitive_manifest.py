"""Generate joint zero-overlap graph and SAT manifests for cost-sensitive confirmation."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from collections import Counter
from experiments.multiagent_capacity_coupling import REPO_ROOT
from experiments.signal.long_diameter_graph import canonical_graph_hash, generate_long_diameter_graph, public_instance as graph_public, reference_engagement, verify_coloring
from experiments.signal.long_diameter_sat import clause_hash, generate_long_diameter_sat, initial_parent_child_mismatches, local_pair_extendability, public_instance as sat_public, verify_sat
SCHEMA='recurrent_parallel_cost_sensitive_confirmation_contract_v1'; STATUS='RPD_COST_SENSITIVE_MANIFESTS_FROZEN'
def R(p):
 v=Path(p); return v if v.is_absolute() else REPO_ROOT/v
def H(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--contract',type=Path,default=Path('specs/recurrent_parallel_cost_sensitive_confirmation_v1.json'));ap.add_argument('--output-dir',type=Path,default=Path('results/recurrent_parallel_cost_sensitive_manifest'));a=ap.parse_args();cp=R(a.contract);c=json.loads(cp.read_text());
 if c.get('schema')!=SCHEMA or c.get('status')!='FROZEN_BEFORE_MANIFEST_AND_OUTCOMES':raise ValueError('joint contract not frozen')
 devp=R(c['development_gate']);dev=json.loads(devp.read_text());
 if dev.get('status')!='RPD_COST_SENSITIVE_GUARD_DEV_GO_CONFIRMATION' or not dev.get('independent_confirmation_authorized'):raise ValueError('joint confirmation blocked')
 oldg=[]
 for p in c['graph']['prior_manifests']:oldg+=json.loads(R(p).read_text())['rows']
 olds=[]
 for p in c['sat']['prior_manifests']:olds+=json.loads(R(p).read_text())['rows']
 oldgh={x['graph_sha256'] for x in oldg}; oldsh={x['clause_sha256'] for x in olds}; gids={x['instance_id'] for x in oldg}; sids={x['instance_id'] for x in olds}
 graph=[]; sat=[]
 for d in (2,4,8,16):
  for i in range(50):
   fg=generate_long_diameter_graph(base_seed=c['graph']['base_seed'],candidate_index=i,diameter=d,split=c['graph']['split']); pg=graph_public(fg); ref=reference_engagement(pg); pg['graph_sha256']=canonical_graph_hash(pg); pg['reference_true_rollbacks']=ref.true_rollbacks; graph.append(pg)
   fs=generate_long_diameter_sat(base_seed=c['sat']['base_seed'],candidate_index=i,diameter=d,split=c['sat']['split']); ps=sat_public(fs); ps['clause_sha256']=clause_hash(ps); ps['initial_mismatches']=initial_parent_child_mismatches(ps); sat.append(ps)
 checks={'graph_200':len(graph)==200,'sat_200':len(sat)==200,'graph_unique':len({x['graph_sha256'] for x in graph})==200,'sat_unique':len({x['clause_sha256'] for x in sat})==200,'graph_zero_overlap':not bool({x['graph_sha256'] for x in graph}&oldgh) and not bool({x['instance_id'] for x in graph}&gids),'sat_zero_overlap':not bool({x['clause_sha256'] for x in sat}&oldsh) and not bool({x['instance_id'] for x in sat}&sids),'graph_fixed':len({(x['n_edges'],x['n_local_edges'],x['n_cross_edges']) for x in graph})==1,'sat_fixed':len({(x['n_clauses'],x['n_local_clauses'],x['n_cross_clauses']) for x in sat})==1,'graph_engaged':all(x['reference_true_rollbacks']>=3 for x in graph),'sat_engaged':all(x['initial_mismatches']>=8 for x in sat),'sat_extendable':all(all(local_pair_extendability(x).values()) for x in sat),'planted_removed':all('planted_assignment' not in x for x in graph+sat)}
 if not all(checks.values()):raise RuntimeError(checks)
 out=R(a.output_dir);out.mkdir(parents=True,exist_ok=True);gp=out/'graph_manifest.json';sp=out/'sat_manifest.json';gp.write_text(json.dumps({'schema':'cost_graph_manifest_v1','status':STATUS,'rows':graph},indent=2,sort_keys=True)+'\n');sp.write_text(json.dumps({'schema':'cost_sat_manifest_v1','status':STATUS,'rows':sat},indent=2,sort_keys=True)+'\n')
 hashes={'graph_manifest':H(gp),'sat_manifest':H(sp),'contract_json':H(cp),'contract_md':H(REPO_ROOT/'specs/recurrent_parallel_cost_sensitive_confirmation_v1.md'),'development_gate':H(devp),'graph_generator':H(REPO_ROOT/'experiments/signal/long_diameter_graph.py'),'sat_generator':H(REPO_ROOT/'experiments/signal/long_diameter_sat.py'),'graph_engine':H(REPO_ROOT/'experiments/recurrent_parallel_core.py'),'sat_engine':H(REPO_ROOT/'experiments/recurrent_parallel_sat_core.py'),'source':H(Path(__file__))}
 p={'schema':'cost_sensitive_joint_generation_v1','status':STATUS,'checks':checks,'graph_counts':dict(Counter(x['partition_diameter'] for x in graph)),'sat_counts':dict(Counter(x['partition_diameter'] for x in sat)),'hashes':hashes};(out/'generation.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n');(out/'GENERATION.md').write_text('# Cost-Sensitive Joint Manifests\n\n## Status: **`'+STATUS+'`**\n\n'+ '\n'.join(f"- `{k}`: **{'PASS' if v else 'FAIL'}**" for k,v in checks.items())+'\n');print(json.dumps({'status':STATUS,'graph':len(graph),'sat':len(sat),'hashes':hashes}))
if __name__=='__main__':main()
