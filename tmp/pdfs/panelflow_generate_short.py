import json
import subprocess
from pathlib import Path

root = Path.cwd()
proc = subprocess.Popen(
    [str(root/'.venv'/'Scripts'/'python.exe'), str(root/'scripts'/'run_mcp_server.py')],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding='utf-8', cwd=root,
)

def req(i, method, params=None):
    packet={'jsonrpc':'2.0','id':i,'method':method}
    if params is not None: packet['params']=params
    proc.stdin.write(json.dumps(packet,ensure_ascii=False)+'\n');proc.stdin.flush()
    while True:
        line=proc.stdout.readline()
        if not line: raise RuntimeError(proc.stderr.read())
        resp=json.loads(line)
        if resp.get('id')==i:return resp

scenes=[
 {'title':'The summons','prompt':'Vertical 9:16, original Vox-inspired clean 2D stick-figure editorial animation. Recurring protagonist: simple black circular head, thin black limbs, small teal scarf. Close-up, sleepy adult stick figure beside bed at 1 a.m.; phone glows with abstract icons, tiny paper courtroom summons slides into foreground. Deep teal night palette, dry visual comedy. One action: paper slides in as camera gently pushes toward phone. Stable lines, no morphing, no readable text, no logos, no dialogue, no soundtrack.'},
 {'title':'The negotiation','prompt':'Vertical 9:16, same clean 2D stick-figure editorial style and same adult protagonist with teal scarf. Bedroom transforms metaphorically into a tiny courtroom: a miniature brain-shaped judge behind a desk raises one blank video card; absurd stack wobbles. Navy and orange palette. One action: judge lifts the card and stack wobbles, slow lateral drift. Preserve character and flat shapes, no readable text, no logos, no dialogue, no soundtrack.'},
 {'title':'No stopping point','prompt':'Vertical 9:16, same original stick-figure animation and teal-scarf protagonist. A conveyor belt of blank rounded video tiles loops into darkness and passes the tired figure; explanatory editorial metaphor, navy and coral. One action: tiles glide steadily as camera tracks the belt. Preserve lines and proportions, no text, logos, dialogue or soundtrack.'},
 {'title':'Change the setup','prompt':'Vertical 9:16, same stick-figure protagonist and 2D editorial style. The adult places their phone on a charging shelf beyond the bedroom doorway; a paper book waits beside the bed in warm lamplight. One action: hand places phone on shelf, gentle camera follow and focus shift to book. No readable text, logos, extra characters or morphing.'},
 {'title':'Small experiment','prompt':'Vertical 9:16, same stick-figure protagonist settles into bed. Three clear floating pictograms appear in order: simple clock, phone resting on distant shelf, open paper book. Mint and indigo palette with generous negative space. One action: icons pop in sequentially as shoulders relax. Locked camera, stable black line art, no words, logos, dialogue or soundtrack.'},
 {'title':'The appeal','prompt':'Vertical 9:16, return to opening bedroom doorway composition, same teal-scarf stick-figure adult walking away from phone shelf. Tiny brain-court judge lifts a blank appeal card; moonlit blue palette. One action: card lifts as camera gently pushes toward the phone, ending on a glowing phone framing that loops to the opening. Stable clean 2D lines, no text, logos, dialogue or soundtrack.'},
]
try:
    init=req(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'Codex','version':'1'}})
    proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');proc.stdin.flush()
    result=req(2,'tools/call',{'name':'panelflow_chronoflow_generate_video','arguments':{
      'prompt':'A concise educational comedy about late-night scrolling, with a useful gentle habit takeaway. Six connected mini-scenes, consistent original stick-figure editorial animation, vertical short, curious opening and satisfying visual loop. No readable in-frame text; narration and captions will be added in post.',
      'workflow_mode':'storyboard','total_duration':31.0,'scenes':scenes,
      'width':768,'height':1344,'steps':4,'lora_choice':'4step','upscale_mode':'none','face_refine':False
    }})
    print(json.dumps(result,ensure_ascii=False,indent=2))
finally:
    proc.terminate();proc.wait(timeout=5)
