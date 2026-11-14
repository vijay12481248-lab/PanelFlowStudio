import json
import subprocess
from pathlib import Path

root = Path.cwd()
python = root / '.venv' / 'Scripts' / 'python.exe'
server = root / 'scripts' / 'run_mcp_server.py'
proc = subprocess.Popen([str(python), str(server)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', cwd=root)

def request(i, method, params=None):
    packet = {'jsonrpc':'2.0','id':i,'method':method}
    if params is not None: packet['params'] = params
    proc.stdin.write(json.dumps(packet)+'\n'); proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line: raise RuntimeError(proc.stderr.read())
        response = json.loads(line)
        if response.get('id') == i: return response

try:
    init=request(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'codex','version':'1'}})
    proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');proc.stdin.flush()
    tools=request(2,'tools/list')['result']['tools']
    wanted = {'panelflow_system_health','panelflow_models_status','panelflow_system_resources','panelflow_chronoflow_generate_image','panelflow_chronoflow_generate_video','panelflow_music_health','panelflow_original_create_story','panelflow_original_direct_shots','panelflow_original_generate_art','panelflow_original_animate','panelflow_original_render_video','panelflow_original_film_frames','panelflow_original_film_clips','panelflow_original_film_score','panelflow_original_film_master','panelflow_original_film_status','panelflow_original_film_job','panelflow_chronoflow_get_job'}
    selected=[{'name':t['name'],'description':t.get('description','')[:350],'inputSchema':t['inputSchema']} for t in tools if any(k in (t['name']+' '+t.get('description','')).lower() for k in ('image','art','music','speech','narration','render','project_create','studio_provider'))]
    print(json.dumps({'initialize':init,'selected_tools':selected},ensure_ascii=False,indent=2))
    for n,name in enumerate(('panelflow_system_health','panelflow_models_status','panelflow_system_resources','panelflow_music_health'),3):
        if name in {t['name'] for t in tools}:
            res=request(n,'tools/call',{'name':name,'arguments':{}})
            payload=res.get('result',{}).get('content',[{}])[0].get('text','')
            try: payload=json.loads(payload)
            except Exception: pass
            print('CALL',name,json.dumps(payload,ensure_ascii=False)[:3000])
finally:
    proc.terminate();proc.wait(timeout=5)
