"""Deterministic recurrent controller with Jacobi proposals and serialized writes."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict,dataclass
import hashlib,json,threading
from typing import Any,Callable,Literal,Protocol

def canonical(value:Any)->str:return json.dumps(value,sort_keys=True,separators=(',',':'),default=str)
def digest(value:Any)->str:return hashlib.sha256(canonical(value).encode()).hexdigest()

@dataclass(frozen=True)
class ToolProposal:
 proposal_id:str
 agent_id:str
 phase:Literal['read','write']
 app_name:str
 api_name:str
 arguments_json:str='{}'
 message_targets:tuple[str,...]=()
 def arguments(self)->dict[str,Any]:
  value=json.loads(self.arguments_json)
  if not isinstance(value,dict):raise TypeError('proposal arguments must decode to an object')
  return value

@dataclass(frozen=True)
class ToolMessage:
 message_id:str
 source_agent:str
 target_agent:str
 proposal_id:str
 created_round:int
 payload_json:str
 payload_sha256:str
 success:bool

@dataclass(frozen=True)
class RoundSnapshot:
 round_index:int
 checkpoint_id:str
 messages:tuple[ToolMessage,...]
 state_sha256:str
 def for_agent(self,agent_id:str)->tuple[ToolMessage,...]:return tuple(x for x in self.messages if x.target_agent in (agent_id,'*'))

@dataclass(frozen=True)
class RoundAudit:
 round_index:int
 checkpoint_id:str
 snapshot_sha256:str
 snapshot_message_count:int
 snapshot_message_ages:tuple[int,...]
 proposal_count:int
 read_count:int
 write_count:int
 proposal_agent_count:int
 max_proposal_concurrency:int
 barrier_reached:bool
 commits_before_barrier:int
 commit_order:tuple[str,...]
 max_write_concurrency:int
 messages_generated:int
 same_round_message_reads:int
 rolled_back:bool
 error_type:str|None
 result_hashes:tuple[str,...]

class EnvironmentAdapter(Protocol):
 def save_state(self,state_id:str)->None:...
 def load_state(self,state_id:str)->None:...
 def state_digest(self)->str:...
 def execute(self,proposal:ToolProposal)->Any:...

ProposalFunction=Callable[[RoundSnapshot],list[ToolProposal]]

class RecurrentBarrierController:
 def __init__(self,adapter:EnvironmentAdapter,run_prefix:str):
  self.adapter=adapter;self.run_prefix=run_prefix;self.round_index=0;self.pending_messages:tuple[ToolMessage,...]=();self.audits:list[RoundAudit]=[]
 def _propose(self,snapshot:RoundSnapshot,functions:dict[str,ProposalFunction])->tuple[list[ToolProposal],int]:
  if not functions:return [],0
  barrier=threading.Barrier(len(functions));lock=threading.Lock();active=0;maximum=0
  def worker(agent_id:str,function:ProposalFunction):
   nonlocal active,maximum
   with lock:active+=1;maximum=max(maximum,active)
   barrier.wait()
   try:
    proposals=function(snapshot)
    if any(x.agent_id!=agent_id for x in proposals):raise ValueError('proposal agent mismatch')
    return proposals
   finally:
    with lock:active-=1
  with ThreadPoolExecutor(max_workers=len(functions)) as pool:
   futures=[pool.submit(worker,a,f) for a,f in sorted(functions.items())]
   groups=[f.result() for f in futures]
  return [x for group in groups for x in group],maximum
 def run_round(self,functions:dict[str,ProposalFunction])->RoundAudit:
  t=self.round_index;checkpoint=f'{self.run_prefix}_round_{t}';self.adapter.save_state(checkpoint);state_sha=self.adapter.state_digest();snapshot=RoundSnapshot(t,checkpoint,self.pending_messages,state_sha);snapshot_sha=digest({'round':t,'messages':[asdict(x) for x in snapshot.messages],'state':state_sha});ages=tuple(t-x.created_round for x in snapshot.messages);proposals,proposal_concurrency=self._propose(snapshot,functions);barrier_reached=True;commits_before_barrier=0
  reads=sorted((x for x in proposals if x.phase=='read'),key=lambda x:(x.agent_id,x.proposal_id));writes=sorted((x for x in proposals if x.phase=='write'),key=lambda x:(x.agent_id,x.proposal_id));generated=[];commit_order=[];result_hashes=[];write_active=0;max_write=0;rolled_back=False;error_type=None
  try:
   for proposal in reads+writes:
    if proposal.phase=='write':write_active+=1;max_write=max(max_write,write_active)
    try:result=self.adapter.execute(proposal)
    finally:
     if proposal.phase=='write':write_active-=1
    result_json=canonical(result);result_sha=hashlib.sha256(result_json.encode()).hexdigest();result_hashes.append(result_sha);commit_order.append(f'{proposal.phase}:{proposal.agent_id}:{proposal.proposal_id}')
    for target in proposal.message_targets:
     generated.append(ToolMessage(f'{t}:{proposal.proposal_id}:{target}',proposal.agent_id,target,proposal.proposal_id,t,result_json,result_sha,True))
  except Exception as exc:
   self.adapter.load_state(checkpoint);rolled_back=True;error_type=type(exc).__name__;generated=[]
  self.pending_messages=tuple(generated);audit=RoundAudit(t,checkpoint,snapshot_sha,len(snapshot.messages),ages,len(proposals),len(reads),len(writes),len(functions),proposal_concurrency,barrier_reached,commits_before_barrier,tuple(commit_order),max_write,len(generated),0,rolled_back,error_type,tuple(result_hashes));self.audits.append(audit);self.round_index+=1;return audit
 def normalized_transcript(self)->list[dict[str,Any]]:
  rows=[]
  for x in self.audits:
   row=asdict(x);row.pop('checkpoint_id');rows.append(row)
  return rows
