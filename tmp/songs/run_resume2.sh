#!/bin/bash
cd "E:/VIJAY SEKAR/PanelFlow Studio"
PY=".venv/Scripts/python.exe"; M="tools/songs/make_songs.py"; IDS="001 003 004 016 018 021 037 038 071 100"; export HF_HUB_OFFLINE=1; L=tmp/songs/resume2.log
echo "[$(date +%H:%M)] score sft 100" >> $L; $PY $M score 100 --model sft >> $L 2>&1
echo "[$(date +%H:%M)] hybrid" >> $L;        $PY $M gen $IDS --model sft --n 4 --cover-from turbo --strength 0.7 --tag hyb70 >> $L 2>&1
echo "[$(date +%H:%M)] score hyb" >> $L;     $PY $M score $IDS --model sft --tag hyb70 >> $L 2>&1
echo "[$(date +%H:%M)] showcase" >> $L;      $PY $M showcase $IDS >> $L 2>&1
echo "RESUME2 FINISHED $(date +%H:%M)" >> $L
