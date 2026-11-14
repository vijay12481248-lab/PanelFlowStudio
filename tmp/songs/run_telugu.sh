#!/bin/bash
cd "E:/VIJAY SEKAR/PanelFlow Studio"
PY=".venv/Scripts/python.exe"; M="tools/songs/make_songs.py"; export HF_HUB_OFFLINE=1; L=tmp/songs/telugu.log
echo "[$(date +%H:%M)] turbo" >> $L;   $PY $M gen 101 --model turbo --n 4 >> $L 2>&1
echo "[$(date +%H:%M)] turboB" >> $L;  $PY $M gen 101 --model turbo --n 4 --tag turboB >> $L 2>&1
echo "[$(date +%H:%M)] sft" >> $L;     $PY $M gen 101 --model sft --n 4 >> $L 2>&1
echo "[$(date +%H:%M)] score" >> $L;   $PY $M score 101 --model turbo >> $L 2>&1; $PY $M score 101 --model turbo --tag turboB >> $L 2>&1
echo "[$(date +%H:%M)] hybrid" >> $L;  $PY $M gen 101 --model sft --n 4 --cover-from turbo --strength 0.7 --tag hyb70 >> $L 2>&1
echo "[$(date +%H:%M)] score rest" >> $L; $PY $M score 101 --model sft >> $L 2>&1; $PY $M score 101 --model sft --tag hyb70 >> $L 2>&1
$PY $M showcase 101 >> $L 2>&1
echo "TELUGU FINISHED $(date +%H:%M)" >> $L
