#!/bin/bash
# score finished songs while generation is still running; stop once all 90 songs are generated and scored
cd "E:/VIJAY SEKAR/PanelFlow Studio"
while true; do
  HF_HUB_OFFLINE=1 ".venv/Scripts/python.exe" tools/songs/make_songs.py score --model turbo >> tmp/songs/score_all_turbo.log 2>&1
  done_gen=$(grep -c "takes in" tmp/songs/gen_all_turbo.log)
  if [ "$done_gen" -ge 90 ]; then
    HF_HUB_OFFLINE=1 ".venv/Scripts/python.exe" tools/songs/make_songs.py score --model turbo >> tmp/songs/score_all_turbo.log 2>&1
    echo FINISHED >> tmp/songs/score_all_turbo.log; break
  fi
  sleep 90
done
