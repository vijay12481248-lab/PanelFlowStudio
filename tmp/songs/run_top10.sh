#!/bin/bash
# Ten showcase songs: turbo x8, sft x4, hybrid (sft re-render of best turbo) x4; score; master best of each family.
cd "E:/VIJAY SEKAR/PanelFlow Studio"
PY=".venv/Scripts/python.exe"; M="tools/songs/make_songs.py"; IDS="001 003 004 016 018 021 037 038 071 100"
export HF_HUB_OFFLINE=1
L=tmp/songs/top10.log
echo "[$(date +%H:%M)] turbo" >> $L;   $PY $M gen $IDS --model turbo --n 4 >> $L 2>&1
echo "[$(date +%H:%M)] turboB" >> $L;  $PY $M gen $IDS --model turbo --n 4 --tag turboB >> $L 2>&1
echo "[$(date +%H:%M)] score turbo while sft generates" >> $L
( $PY $M score $IDS --model turbo >> $L 2>&1; $PY $M score $IDS --model turbo --tag turboB >> $L 2>&1 ) &
$PY $M gen $IDS --model sft --n 4 >> $L 2>&1
wait
echo "[$(date +%H:%M)] score sft" >> $L; $PY $M score $IDS --model sft >> $L 2>&1
echo "[$(date +%H:%M)] hybrid" >> $L;    $PY $M gen $IDS --model sft --n 4 --cover-from turbo --strength 0.7 --tag hyb70 >> $L 2>&1
echo "[$(date +%H:%M)] score hyb" >> $L; $PY $M score $IDS --model sft --tag hyb70 >> $L 2>&1
echo "[$(date +%H:%M)] showcase" >> $L;  $PY $M showcase $IDS >> $L 2>&1
echo "TOP10 FINISHED $(date +%H:%M)" >> $L
