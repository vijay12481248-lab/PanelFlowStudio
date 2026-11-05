# PanelFlow Studio - ComfyUI Model Downloader (PowerShell)
# Usage:
#   .\scripts\download_models.ps1 -Suite qwen
#   .\scripts\download_models.ps1 -Suite flux
#   .\scripts\download_models.ps1 -Suite all

param(
    [ValidateSet("qwen", "flux", "all")]
    [string]$Suite = "qwen",
    [string]$ComfyDir = "E:\VIJAY SEKAR\ComfyUI"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " PanelFlow Studio - Model Downloader (ComfyUI)" -ForegroundColor Cyan
Write-Host " Target Directory: $ComfyDir" -ForegroundColor Cyan
Write-Host " Selected Suite:   $Suite" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

function Download-ModelFile {
    param(
        [string]$Url,
        [string]$Subfolder,
        [string]$Filename,
        [string]$Description
    )

    $targetDir = Join-Path $ComfyDir "models\$Subfolder"
    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }

    $targetFile = Join-Path $targetDir $Filename

    if (Test-Path $targetFile) {
        $size = (Get-Item $targetFile).Length
        if ($size -gt 10MB) {
            Write-Host "[=] Already exists: $Filename ($([math]::Round($size/1GB, 2)) GB) - Skipping." -ForegroundColor Green
            return
        }
    }

    Write-Host "`n[+] Downloading: $Description" -ForegroundColor Yellow
    Write-Host "    Target: $targetFile" -ForegroundColor DarkGray
    Write-Host "    Source: $Url" -ForegroundColor DarkGray

    # Use curl.exe with resume (-C -), follow redirects (-L), and retry
    & curl.exe -L -C - --retry 5 --retry-delay 3 -o "$targetFile" "$Url"

    if ($LASTEXITCODE -eq 0 -and (Test-Path $targetFile)) {
        $finalSize = (Get-Item $targetFile).Length
        Write-Host "[✓] Download complete: $Filename ($([math]::Round($finalSize/1GB, 2)) GB)" -ForegroundColor Green
    } else {
        Write-Host "[!] Download failed or was interrupted for: $Filename" -ForegroundColor Red
        Write-Host "    You can run this script again anytime to resume!" -ForegroundColor Yellow
    }
}

# 1. Qwen 2.5-VL + LongCat-Image Suite
if ($Suite -eq "qwen" -or $Suite -eq "all") {
    Write-Host "`n>>> [QWEN 2.5-VL + LONGCAT SUITE] <<<" -ForegroundColor Magenta

    # Qwen 2.5-VL 7B FP8 Text Encoder
    Download-ModelFile `
        -Url "https://huggingface.co/Comfy-Org/Qwen-Image/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors" `
        -Subfolder "text_encoders" `
        -Filename "qwen_2.5_vl_7b_fp8_scaled.safetensors" `
        -Description "Qwen 2.5-VL 7B FP8 Text Encoder (~7.6 GB)"

    # LongCat-Image Diffusion Backbone (Matches workflow_registry.json filename)
    Download-ModelFile `
        -Url "https://huggingface.co/Comfy-Org/LongCat-Image/resolve/main/split_files/diffusion_models/longcat_image_bf16.safetensors" `
        -Subfolder "diffusion_models" `
        -Filename "longcat_image_bf16_3.safetensors" `
        -Description "LongCat-Image Diffusion Model (~12.5 GB)"

    # AE VAE
    Download-ModelFile `
        -Url "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors" `
        -Subfolder "vae" `
        -Filename "ae.safetensors" `
        -Description "AE VAE AutoEncoder (~335 MB)"
}

# 2. FLUX.1 [schnell] Suite
if ($Suite -eq "flux" -or $Suite -eq "all") {
    Write-Host "`n>>> [FLUX.1 SCHNELL SUITE (Apache 2.0)] <<<" -ForegroundColor Magenta

    # FLUX.1 schnell FP8
    Download-ModelFile `
        -Url "https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors" `
        -Subfolder "diffusion_models" `
        -Filename "flux1-schnell-fp8.safetensors" `
        -Description "FLUX.1 [schnell] FP8 Diffusion Model (~11.9 GB)"

    # T5-XXL FP8 Text Encoder
    Download-ModelFile `
        -Url "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" `
        -Subfolder "text_encoders" `
        -Filename "t5xxl_fp8_e4m3fn.safetensors" `
        -Description "T5-XXL FP8 Text Encoder (~4.9 GB)"

    # CLIP-L Text Encoder
    Download-ModelFile `
        -Url "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" `
        -Subfolder "text_encoders" `
        -Filename "clip_l.safetensors" `
        -Description "CLIP-L Text Encoder (~246 MB)"

    # AE VAE
    Download-ModelFile `
        -Url "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors" `
        -Subfolder "vae" `
        -Filename "ae.safetensors" `
        -Description "AE VAE AutoEncoder (~335 MB)"

    # PuLID for FLUX (Character Consistency)
    Download-ModelFile `
        -Url "https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors" `
        -Subfolder "pulid" `
        -Filename "pulid_flux_v0.9.1.safetensors" `
        -Description "PuLID for FLUX Character Consistency (~300 MB)"
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " Download finished! All models placed in $ComfyDir\models" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
