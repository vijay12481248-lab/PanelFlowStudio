"""Opt-in live production API acceptance; never logs authentication headers."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from typing import Any
import httpx

BASE = Path(os.environ['LOCALAPPDATA']) / 'hermes/cache/scratch/release-acceptance-20261021'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--phase', choices=['discover', 'create', 'narrate', 'export', 'verify'], default='discover')
    args = parser.parse_args()
    root = args.evidence or BASE / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    evidence = root / 'evidence.json'
    data = json.loads(evidence.read_text()) if evidence.exists() else {'root':str(root), 'operations':[]}
    def save():
        evidence.write_text(json.dumps(data, indent=2), encoding='utf-8')
    token = (Path(os.environ['LOCALAPPDATA']) / 'PanelFlow Studio/engine.token').read_text().strip()
    client = httpx.Client(base_url='http://127.0.0.1:8765', headers={'X-PanelFlow-Token':token}, timeout=240, trust_env=False)
    def comparable_state(state):
        state=json.loads(json.dumps(state))
        state.get('panel_review_sync',{}).pop('synced_at',None)
        return state
    def api(method, path, payload=None) -> Any:
        resp = client.request(method, path, json=payload) if payload is not None else client.request(method,path)
        try: result=resp.json()
        except ValueError: result={'body':resp.text[:1000]}
        data['operations'].append({'time':time.time(),'method':method,'path':path,'request':payload,'status':resp.status_code,'response':result})
        save()
        resp.raise_for_status()
        return result
    try:
        if args.phase == 'discover':
            data['health']=api('GET','/api/system/health')
            data['providers']=api('GET','/api/audio/providers')
            from engine.audio.synthesis import CHATTERBOX_PYTHON, VOICE_REF_DIR, TOOLS_ROOT
            from engine.system.setup import locate_and_configure_ffmpeg
            data['local_metadata']={'tools_root':str(TOOLS_ROOT),'chatterbox_python':str(CHATTERBOX_PYTHON),'python_exists':CHATTERBOX_PYTHON.exists(),'voice_ref_dir':str(VOICE_REF_DIR),'voice_files':[p.name for p in VOICE_REF_DIR.glob('*') if p.is_file()]}
            data['media_tools']=locate_and_configure_ffmpeg()
            save()
        elif args.phase == 'create':
            from PIL import Image, ImageDraw
            source = root/'input'; source.mkdir(exist_ok=True)
            image=Image.new('RGB',(1280,720),(22,38,62)); draw=ImageDraw.Draw(image)
            draw.rectangle((80,80,1200,640),outline=(94,217,193),width=12)
            draw.ellipse((450,150,830,530),fill=(220,170,60))
            draw.text((120,590),'PanelFlow real narration and export acceptance',fill='white')
            image.save(source/'acceptance.jpg',format='JPEG',quality=94)
            data['source_sha256']=hashlib.sha256((source/'acceptance.jpg').read_bytes()).hexdigest()
            project=api('POST','/api/projects',{'title':'QA Release Acceptance 20261021 '+root.name[:12],'source_type':'LOCAL_FOLDER','source_url':str(source),'rights_status':'USER_OWNED','license_info':'Original geometric QA artwork created for authorized local acceptance.','settings':{'project_path':str(root/'project'),'tts_provider':'chatterbox_turbo'}})
            data['project']=project; save()
            pid=project['id']; api('GET',f'/api/projects/{pid}')
            data['acquisition']=api('POST',f'/api/projects/{pid}/acquire')
            save()
        elif args.phase == 'narrate':
            pid=data['project']['id']
            text='At sunrise, a golden light crossed the quiet valley.'
            data['narration_request']={'segment_id':'acceptance_narration','text':text,'voice':'The Narrator','emotion':'Neutral','intensity':0.5,'speed':1.0,'text_revision':1,'content_hash':hashlib.sha256(text.encode()).hexdigest(),'force':False}; save()
            data['narration']=api('POST',f'/api/projects/{pid}/narration/synthesize-segment',data['narration_request']); save()
        elif args.phase == 'export':
            import math
            pid=data['project']['id']
            job_id=data['acquisition']['job_id']
            acquired=api('GET',f'/api/jobs/{job_id}')
            assert acquired['status']=='SUCCEEDED', acquired
            pages=api('GET',f'/api/projects/{pid}/pages')
            assert len(pages)==1 and pages[0]['status']=='READY', pages
            page=pages[0]
            image_response=client.get(page['image_url']); image_response.raise_for_status()
            assert hashlib.sha256(image_response.content).hexdigest()==page['sha256']
            data['pages']=pages
            duration=math.ceil((data['narration']['measured_duration_sec']+0.5)*30)/30
            clip={'id':'acceptance_narration','scene_id':'acceptance_scene','speaker':'The Narrator','text':data['narration_request']['text'],'start_time_sec':0.0,'duration_sec':data['narration']['measured_duration_sec'],'audio_url':data['narration']['audio_url'],'status':'READY','review_status':'APPROVED','text_revision':1,'generated_audio_revision':1,'content_hash':data['narration_request']['content_hash']}
            state={'schema_version':2,'project_id':pid,'aspect_ratio':'16:9','fps':30,'scenes':[{'id':'acceptance_scene','title':'Original QA artwork','start_time_sec':0.0,'duration_sec':duration,'transition_in':'none','layers':[{'id':'acceptance_layer','name':'Original QA artwork','source_page_id':page['id'],'page_sequence':1,'image_url':page['image_url'],'crop':{'x':0,'y':0,'width':1280,'height':720},'transform':{'x':0,'y':0,'scale':1.0,'rotation':0.0,'opacity':1.0,'z_index':0},'start_offset_sec':0.0,'duration_sec':duration,'motion_preset':'none','visible':True}]}],'narration_clips':[clip],'bgm_tracks':[],'sfx_cues':[]}
            saved=api('PUT',f'/api/projects/{pid}/story-editor',{'state':state})
            readback=api('GET',f'/api/projects/{pid}/story-editor')
            assert comparable_state(readback['state'])==comparable_state(saved['state'])
            state=readback['state']; data['editor_state']=state; save()
            request={'profile_name':'draft_720p','subtitle_enabled':False,'bgm_volume_db':-10.0,'dialogue_gain_db':0.0,'is_draft':True,'timeline_data':state}
            preflight=api('POST',f'/api/projects/{pid}/render/preflight',request)
            assert preflight['valid'] and preflight['stats']['narration_approved']==1 and not preflight['warnings'], preflight
            data['render']=api('POST',f'/api/projects/{pid}/render/jobs',request); save()
            rid=data['render']['render_id']
            deadline=time.monotonic()+240
            while time.monotonic()<deadline:
                result=api('GET',f'/api/projects/{pid}/render/jobs/{rid}')
                data['render']=result; save()
                if result['status'] not in ('QUEUED','RUNNING'): break
                time.sleep(2)
            assert data['render']['status'] in ('SUCCEEDED','COMPLETE'),data['render']
        elif args.phase == 'verify':
            import io
            import numpy as np
            import soundfile as sf
            from PIL import Image
            pid=data['project']['id']; rid=data['render']['render_id']
            render=api('GET',f'/api/projects/{pid}/render/jobs/{rid}')
            assert render['status'] in ('SUCCEEDED','COMPLETE') and render['validation_status']=='VALID'
            data['render']=render
            data['render_validation']=api('GET',f'/api/projects/{pid}/render/jobs/{rid}/validation')
            data['render_history']=api('GET',f'/api/projects/{pid}/render/jobs')
            assert any(r['render_id']==rid and r['status'] in ('SUCCEEDED','COMPLETE') for r in data['render_history'])
            data['editor_reopen']=api('GET',f'/api/projects/{pid}/story-editor')
            assert comparable_state(data['editor_reopen']['state'])==comparable_state(data['editor_state'])
            artifacts={}
            for name,path,url in [('narration',Path(data['narration']['audio_path']),data['narration']['audio_url']),('video',Path(render['output_path']),f'/api/projects/{pid}/render/jobs/{rid}/output')]:
                blob=path.read_bytes(); streamed=client.get(url); streamed.raise_for_status()
                digest=hashlib.sha256(blob).hexdigest(); assert digest==hashlib.sha256(streamed.content).hexdigest()
                probe=subprocess.run([data['media_tools']['ffprobe_path'],'-v','error','-show_format','-show_streams','-of','json',str(path)],capture_output=True,text=True,check=True)
                info=json.loads(probe.stdout)
                decode=subprocess.run([data['media_tools']['ffmpeg_path'],'-v','error','-xerror','-i',str(path),'-f','null','-'],capture_output=True,text=True)
                artifacts[name]={'path':str(path),'size':len(blob),'sha256':digest,'http_status':streamed.status_code,'http_sha256_match':True,'probe':info,'decode_exit':decode.returncode,'decode_stderr':decode.stderr}
                data['artifacts']=artifacts; save(); assert decode.returncode==0,decode.stderr
                if name=='narration':
                    samples,rate=sf.read(io.BytesIO(blob)); artifacts[name]['peak']=float(np.max(np.abs(samples))); artifacts[name]['rms']=float(np.sqrt(np.mean(samples**2)))
                    assert artifacts[name]['rms']>0.001
                else:
                    video=next(s for s in info['streams'] if s['codec_type']=='video'); audio=next(s for s in info['streams'] if s['codec_type']=='audio')
                    assert (video['width'],video['height'])==(1280,720)
                    assert video['codec_name']=='h264' and audio['codec_name']=='aac'
                    assert abs(float(info['format']['duration'])-data['editor_state']['scenes'][0]['duration_sec'])<0.15
                    pcm=subprocess.run([data['media_tools']['ffmpeg_path'],'-v','error','-i',str(path),'-vn','-f','f32le','-ac','1','-ar','24000','pipe:1'],capture_output=True,check=True)
                    values=np.frombuffer(pcm.stdout,dtype='<f4'); artifacts[name]['audio_rms']=float(np.sqrt(np.mean(values**2))); assert artifacts[name]['audio_rms']>0.001
            sheet=client.get(f'/api/projects/{pid}/render/jobs/{rid}/contact-sheet');sheet.raise_for_status()
            sheet_path=root/'contact-sheet.jpg';sheet_path.write_bytes(sheet.content)
            with Image.open(io.BytesIO(sheet.content)) as image: image.load(); data['contact_sheet']={'path':str(sheet_path),'size':image.size,'sha256':hashlib.sha256(sheet.content).hexdigest()}
            data['final_health']=api('GET','/api/system/health')
            assert data['final_health']['instance_id']==data['health']['instance_id']
            data['verified']=True; save()
    except Exception as exc:
        data.setdefault('errors',[]).append({'phase':args.phase,'type':type(exc).__name__,'message':str(exc)})
        save()
        print(json.dumps({'evidence':str(evidence),'phase':args.phase,'error':str(exc)}))
        raise
    print(json.dumps({'evidence':str(evidence),'phase':args.phase,'project_id':data.get('project',{}).get('id'),'result':'recorded'}))

if __name__=='__main__': main()
