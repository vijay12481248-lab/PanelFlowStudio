#!/bin/bash
# Resume the ten-song run: wait for the server and for ComfyUI to be idle (it shares the GPU), then do only the missing steps.
cd "E:/VIJAY SEKAR/PanelFlow Studio"
PY=".venv/Scripts/python.exe"; M="tools/songs/make_songs.py"; IDS="001 003 004 016 018 021 037 038 071 100"; export HF_HUB_OFFLINE=1; L=tmp/songs/resume.log
for i in $(seq 1 120); do curl -s -m 3 http://127.0.0.1:8001/health | grep -q '"llm_initialized":true' && break; sleep 5; done
echo "[$(date +%H:%M)] server ready; waiting for ComfyUI idle (max 90 min)" >> $L
for i in $(seq 1 90); do
  r=$(curl -s -m 5 http://127.0.0.1:8188/queue | $PY -c "import sys,json;print(len(json.load(sys.stdin)['queue_running']))" 2>/dev/null)
  [ "${r:-0}" = "0" ] && break; sleep 60
done
echo "[$(date +%H:%M)] sft 100" >> $L;     $PY $M gen 100 --model sft --n 4 >> $L 2>&1
$PY $M score 100 --model sft >> $L 2>&1
echo "[$(date +%H:%M)] hybrid" >> $L;      $PY $M gen $IDS --model sft --n 4 --cover-from turbo --strength 0.7 --tag hyb70 >> $L 2>&1
echo "[$(date +%H:%M)] score hyb" >> $L;   $PY $M score $IDS --model sft --tag hyb70 >> $L 2>&1
echo "[$(date +%H:%M)] showcase" >> $L;    $PY $M showcase $IDS >> $L 2>&1
echo "RESUME FINISHED $(date +%H:%M)" >> $L
