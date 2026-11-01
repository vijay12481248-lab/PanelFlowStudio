# Train the comic line reader, resuming from the newest checkpoint if the data loader dies (up to 6 tries).
# Usage: powershell -File scripts/ocr_train/run_training.ps1 <run_dir> <eval_dir> [steps]
param([string]$Run, [string]$Eval, [int]$Steps = 6000)
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
for ($try = 0; $try -lt 6; $try++) {
    # --resume is a no-op on a fresh run folder, and guarantees an existing checkpoint is never overwritten.
    & .\.venv\Scripts\python.exe -u scripts/ocr_train/train_trocr.py $Run $Eval --steps $Steps --batch 48 --eval_every 1000 --save_every 500 --publish --resume
    if ($LASTEXITCODE -eq 0) { exit 0 }
    Write-Host "TRAINING EXITED $LASTEXITCODE - resuming (try $($try + 1))"
    Start-Sleep -Seconds 5
}
exit 1
