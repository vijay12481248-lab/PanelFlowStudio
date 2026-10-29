import io
import os
import tempfile
from pathlib import Path
from PIL import Image
import pytest
from fastapi.testclient import TestClient

from engine.api.app import create_app
from engine.imaging.browser_ai_bridge import (
    BrowserAIBridge,
    detect_platform_preset,
    SUPPORTED_PRESETS,
    UNIVERSAL_PRESET,
)


def test_detect_platform_preset():
    assert detect_platform_preset("https://chatgpt.com").id == "chatgpt"
    assert detect_platform_preset("https://chat.openai.com/c/123").id == "chatgpt"
    assert detect_platform_preset("https://gemini.google.com/app").id == "gemini"
    assert detect_platform_preset("https://www.meta.ai/").id == "meta_ai"
    assert detect_platform_preset("https://claude.ai/chat").id == "claude"
    assert detect_platform_preset("https://my-custom-ai-tool.internal/").id == "universal"


def test_get_status():
    bridge = BrowserAIBridge()
    status = bridge.get_status()
    assert "playwright_installed" in status
    assert status["playwright_installed"] is True
    assert "presets" in status
    assert len(status["presets"]) == len(SUPPORTED_PRESETS)
    assert status["preferred_channel"] in ("chrome", "msedge", "chromium")


def test_browser_ai_bridge_end_to_end_mock(tmp_path):
    """
    Spins up a lightweight mock page server/data-url and tests prompt injection,
    simulated generation completion, and high-res image & text extraction.
    """
    from playwright.sync_api import sync_playwright

    bridge = BrowserAIBridge(profile_dir=tmp_path / "browser_profile")
    output_dir = tmp_path / "extracted_assets"

    # Create a tiny 1x1 red PNG base64 to simulate AI generated image
    img_byte_arr = io.BytesIO()
    Image.new("RGB", (256, 256), color=(255, 60, 60)).save(img_byte_arr, format="PNG")
    import base64
    b64_img = base64.b64encode(img_byte_arr.getvalue()).decode("ascii")
    data_img_src = f"data:image/png;base64,{b64_img}"

    html_file = tmp_path / "mock_ai.html"
    html_file.write_text(f"""
    <!DOCTYPE html>
    <html>
      <head><title>Mock AI</title></head>
      <body>
        <div id="editable" contenteditable="true" role="textbox" style="min-height:40px; border:1px solid #ccc;"></div>
        <button id="send-btn" aria-label="Send prompt" onclick="handleGenerate()">Send</button>
        <button id="stop-btn" style="display:none;">Stop</button>
        <div id="response-box" class="response"></div>

        <script>
          const ed = document.getElementById('editable');
          const btn = document.getElementById('send-btn');
          const stopBtn = document.getElementById('stop-btn');
          const box = document.getElementById('response-box');

          ed.addEventListener('input', () => {{
            btn.disabled = ed.innerText.trim().length === 0;
          }});
          ed.addEventListener('keydown', (e) => {{
            if (e.key === 'Enter') handleGenerate();
          }});

          function handleGenerate() {{
            btn.style.display = 'none';
            stopBtn.style.display = 'inline-block';

            setTimeout(() => {{
              stopBtn.style.display = 'none';
              btn.style.display = 'inline-block';
              box.innerHTML = `
                <p>Generated fantasy character prompt successfully.</p>
                <img id="ai-res" src="{data_img_src}" width="256" height="256" alt="Generated martial hero">
              `;
            }}, 400);
          }}
        </script>
      </body>
    </html>
    """, encoding="utf-8")

    mock_url = html_file.as_uri()

    result = bridge.execute_prompt(
        url=mock_url,
        prompt="A legendary martial emperor summoning thunder",
        extract_type="all",
        output_dir=output_dir,
        headless=True,
        timeout_sec=15.0,
    )

    assert result.success is True, f"Execution failed: {result.error}"
    assert "Generated fantasy character" in result.text_response
    assert len(result.images) == 1
    extracted_img = result.images[0]
    assert extracted_img.width == 256
    assert extracted_img.height == 256
    assert Path(extracted_img.file_path).exists()
    assert extracted_img.byte_size > 100
    assert result.execution_time_sec > 0.0


def test_browser_bridge_api_routes():
    app = create_app()
    client = TestClient(app)

    # 1. Test status route
    resp = client.get("/api/browser-bridge/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["playwright_installed"] is True
    assert len(data["presets"]) > 0

    # 2. Test execute route with invalid schema
    bad_resp = client.post("/api/browser-bridge/execute", json={"url": "not-a-valid-url"})
    assert bad_resp.status_code == 422  # validation error: missing prompt
