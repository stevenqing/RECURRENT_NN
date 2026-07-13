"""Harvest deployment-visible recurrent correction states for a frozen model judge."""
from __future__ import annotations
import hashlib, json
from typing import Any, Mapping
from experiments.recurrent_parallel_core import LocalAgentState,_adjacency,_candidate_assignment,_candidate_cost,_enumerate_local_candidates,_message_for_child,_propose,_root_tree
from experiments.recurrent_parallel_sat_core import SATLocalState,_candidate_assignment as sat_assignment,_candidate_cost as sat_cost,_cross_clauses_by_child,_initial_candidate_index,_local_candidates,_propose as sat_propose
from experiments.signal.long_diameter_graph import verify_coloring
from experiments.signal.long_diameter_sat import verify_sat

def _hash(text):return hashlib.sha256(text.encode()).hexdigest()
def visible_correction_label(prompt:str,substrate:str)->bool:
 lines=prompt.splitlines()
 def field(name):return json.loads(next(x.split('=',1)[1] for x in lines if x.startswith(name+'=')))
 current={int(k):int(v) for k,v in field('local_assignment').items()};alternatives=[{int(k):int(v) for k,v in z.items()} for z in field('candidate_alternatives')];parent={int(k):int(v) for k,v in field('parent_message').items()}
 if current not in alternatives:raise ValueError('current assignment missing from visible alternatives')
 if substrate=='graph':
  constraints=field('cross_edges')
  def cost(candidate):
   assignment={**parent,**candidate};return sum(int(u in assignment and v in assignment and assignment[u]==assignment[v]) for u,v in constraints)
 elif substrate=='sat':
  constraints=field('boundary_clauses')
  def cost(candidate):
   assignment={**parent,**candidate}
   if any(abs(lit) not in assignment for clause in constraints for lit in clause):raise ValueError('boundary literal absent from visible assignments')
   return sum(not any(bool(assignment[abs(lit)])==(lit>0) for lit in clause) for clause in constraints)
 else:raise ValueError(substrate)
 return cost(current)>min(map(cost,alternatives))
def _graph_prompt(instance,state,message,agent,round_index,cross_edges):
 local=_candidate_assignment(state);alternatives=[dict(zip(state.vertices,c)) for c in state.candidates];owned=set(state.vertices);local_edges=[[u,v] for u,v in instance['edges'] if u in owned and v in owned];return '\n'.join(['Recurrent parallel graph-color correction judge. Return JSON only.','Decide whether the current local assignment should change to a listed locally valid candidate that better satisfies the received parent boundary constraints.','Schema: {"needs_correction": boolean, "confidence": number between 0 and 1}','Confidence means the probability that your emitted Boolean decision is correct.',f"diameter={instance['partition_diameter']}; round={round_index}; agent={agent}",f"local_assignment={json.dumps(local,sort_keys=True)}",f"candidate_alternatives={json.dumps(alternatives,sort_keys=True,separators=(',',':'))}",f"local_edges={json.dumps(local_edges,separators=(',',':'))}",f"parent_message={json.dumps(message,sort_keys=True)}",f"cross_edges={json.dumps(cross_edges,separators=(',',':'))}"])
def _sat_prompt(instance,state,message,agent,round_index,clauses):
 local=sat_assignment(state);alternatives=[dict(zip(state.variables,c)) for c in state.candidates];owned=set(state.variables);local_clauses=[c for c in instance['clauses'] if all(abs(x) in owned for x in c)];return '\n'.join(['Recurrent parallel SAT correction judge. Return JSON only.','Boolean assignments use 0=false and 1=true; a negative literal is satisfied when its variable is false.','Decide whether the current local assignment should change to a listed locally valid candidate that better satisfies the received parent-boundary clauses.','Schema: {"needs_correction": boolean, "confidence": number between 0 and 1}','Confidence means the probability that your emitted Boolean decision is correct.',f"diameter={instance['partition_diameter']}; round={round_index}; agent={agent}",f"local_assignment={json.dumps(local,sort_keys=True)}",f"candidate_alternatives={json.dumps(alternatives,sort_keys=True,separators=(',',':'))}",f"local_clauses={json.dumps(local_clauses,separators=(',',':'))}",f"parent_message={json.dumps(message,sort_keys=True)}",f"boundary_clauses={json.dumps(clauses,separators=(',',':'))}"])
def harvest_graph(instance:Mapping[str,Any],round_cap=32):
 n=instance['n_partitions'];parts=instance['partitions'];adj=_adjacency(instance['n_vertices'],instance['edges']);parent,_,_,_=_root_tree(n,instance['partition_tree_edges'],0);states={}
 for a in range(n):
  vs=tuple(v for v,o in enumerate(parts) if o==a);states[a]=LocalAgentState(a,vs,_enumerate_local_candidates(vs,instance['k'],adj))
 incoming={a:{} for a in states};rows=[]
 for t in range(round_cap):
  proposals={}
  for a,state in states.items():
   msg=dict(incoming[a])
   if parent[a] is None or not msg:proposals[a]=(state.candidate_index,state.tie_cursor);continue
   costs=[_candidate_cost(state,i,msg,adj) for i in range(len(state.candidates))];truth=costs[state.candidate_index]>min(costs);pedges=[[u,v] for u,v in instance['edges'] if (u in state.vertices and v in msg) or (v in state.vertices and u in msg)];prompt=_graph_prompt(instance,state,msg,a,t,pedges);rows.append({'sample_key':f"graph::{instance['instance_id']}::{t}::{a}",'substrate':'graph','instance_id':instance['instance_id'],'partition_diameter':instance['partition_diameter'],'round':t,'agent':a,'label':bool(truth),'prompt':prompt,'prompt_sha256':_hash(prompt)});proposals[a]=_propose(state,msg,adj,reset_state=False)
  for a,(sel,cursor) in proposals.items():states[a].candidate_index=sel;states[a].tie_cursor=cursor
  incoming={a:{} for a in states}
  for child,p in parent.items():
   if p is not None:incoming[child]=_message_for_child(states[p],states[child],adj)
  assignment={v:c for st in states.values() for v,c in _candidate_assignment(st).items()}
  if verify_coloring(instance,assignment):break
 return rows
def harvest_sat(instance:Mapping[str,Any],round_cap=32):
 n=instance['n_partitions'];parent,_,_,_=_root_tree(n,instance['partition_tree_edges'],0);cross=_cross_clauses_by_child(instance,parent);codes={int(a):int(c) for a,c in instance['initial_pair_codes'].items()};states={}
 for a in range(n):
  cs=_local_candidates(instance,a);vs=tuple(a*instance['variables_per_partition']+o+1 for o in range(instance['variables_per_partition']));states[a]=SATLocalState(a,vs,cs,_initial_candidate_index(cs,codes[a]))
 incoming={a:{} for a in states};rows=[]
 for t in range(round_cap):
  proposals={}
  for a,state in states.items():
   msg=dict(incoming[a])
   if parent[a] is None or not msg:proposals[a]=(state.candidate_index,state.tie_cursor);continue
   costs=[sat_cost(state,i,msg,cross[a]) for i in range(len(state.candidates))];truth=costs[state.candidate_index]>min(costs);prompt=_sat_prompt(instance,state,msg,a,t,cross[a]);rows.append({'sample_key':f"sat::{instance['instance_id']}::{t}::{a}",'substrate':'sat','instance_id':instance['instance_id'],'partition_diameter':instance['partition_diameter'],'round':t,'agent':a,'label':bool(truth),'prompt':prompt,'prompt_sha256':_hash(prompt)});proposals[a]=sat_propose(state,msg,cross[a])
  for a,(sel,cursor) in proposals.items():states[a].candidate_index=sel;states[a].tie_cursor=cursor
  incoming={a:{} for a in states}
  for child,p in parent.items():
   if p is not None:
    pa=sat_assignment(states[p]);incoming[child]={states[p].variables[0]:pa[states[p].variables[0]],states[p].variables[1]:pa[states[p].variables[1]]}
  assignment={v:x for st in states.values() for v,x in sat_assignment(st).items()}
  if verify_sat(instance,assignment):break
 return rows
