import json, subprocess, sys
from pathlib import Path
root=Path.cwd(); job_id=sys.argv[1]
proc=subprocess.Popen([str(root/'.venv'/'Scripts'/'python.exe'),str(root/'scripts'/'run_mcp_server.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',cwd=root)
def req(i,m,p=None):
 q={'jsonrpc':'2.0','id':i,'method':m};
 if p is not None:q['params']=p
 proc.stdin.write(json.dumps(q)+'\n');proc.stdin.flush()
 while True:
  line=proc.stdout.readline()
  if not line:raise RuntimeError(proc.stderr.read())
  r=json.loads(line)
  if r.get('id')==i:return r
try:
 req(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'Codex','version':'1'}})
 proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');proc.stdin.flush()
 r=req(2,'tools/call',{'name':'panelflow_chronoflow_get_job','arguments':{'job_id':job_id}})
 s=r.get('result',{}).get('content',[{}])[0].get('text','')
 try:print(json.dumps(json.loads(s),ensure_ascii=False,indent=2))
 except Exception:print(s)
finally:proc.terminate();proc.wait(timeout=5)
