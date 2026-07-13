"""Environment-native AppWorld API trace recording with pre-write checkpoints."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import faulthandler,hashlib,json
from typing import Any

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),default=str)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
@dataclass(frozen=True)
class LiveCall:
 index:int
 app_name:str
 api_name:str
 method:str
 arguments:dict[str,Any]
 response:Any
 checkpoint_id:str|None
 arguments_sha256:str
 response_sha256:str
class LiveTraceRecorder:
 def __init__(self,world,prefix='live'):
  self.world=world;self.prefix=prefix;self.calls=[];self._original=None;self._docs={}
 def method(self,app,api):
  key=(app,api)
  if key not in self._docs:
   from appworld.api_docs import prepare_api_docs
   docs=prepare_api_docs(app,include_private_apis=True);self._docs.update({(app,x['api_name']):str(x['method']).lower() for x in docs})
  return self._docs[key]
 def _save_checkpoint(self,method,api,index):
  if method=='get' or any(x in api.lower() for x in ('login','auth','token')):return None
  checkpoint=f'{self.prefix}_before_{index}';original_enable=faulthandler.enable;faulthandler.enable=lambda *args,**kwargs:None
  try:self.world.safety_guard.disable()
  finally:faulthandler.enable=original_enable
  try:self.world.save_state(checkpoint)
  finally:self.world.safety_guard.enable()
  return checkpoint
 def __enter__(self):
  self._original=self.world.requester.request
  def wrapped(*args,**kwargs):
    app=kwargs.get('_app_name',args[0] if args else None);api=kwargs.get('_api_name',args[1] if len(args)>1 else None);payload={k:v for k,v in kwargs.items() if k not in {'_app_name','_api_name','client','raise_on_failure','show','track'}};method=self.method(app,api);index=len(self.calls);checkpoint=self._save_checkpoint(method,api,index);response=self._original(*args,**kwargs);arguments_snapshot=json.loads(canonical(payload));response_snapshot=json.loads(canonical(response));self.calls.append(LiveCall(index,app,api,method,arguments_snapshot,response_snapshot,checkpoint,digest(arguments_snapshot),digest(response_snapshot)));return response
  self.world.requester.request=wrapped;return self
 def __exit__(self,*exc):
  if self._original is not None:self.world.requester.request=self._original
 def public_summary(self):return [{'index':x.index,'method':x.method,'app_hash':hashlib.sha256(x.app_name.encode()).hexdigest(),'api_hash':hashlib.sha256(x.api_name.encode()).hexdigest(),'checkpoint':x.checkpoint_id is not None,'arguments_sha256':x.arguments_sha256,'response_sha256':x.response_sha256} for x in self.calls]
 def to_private_dict(self):return [asdict(x) for x in self.calls]
