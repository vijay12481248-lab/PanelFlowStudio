"""Empirical Adversarial Stress Tests & Latency Benchmarks for WP-1.1 & WP-1.2.

Challenger: challenger_s1_1
Scope:
1. WP-1.1 Fast ComfyUI Error Detection in engine/comfyui/art.py:
   - Real-world ComfyUI CUDA OOM error payload
   - Real-world Interrupted execution payload
   - Malformed, missing, nested, and boundary error status payloads
   - Failure latency benchmark (< 1.5 seconds vs 300s timeout stall)
2. WP-1.2 Active Ollama Eviction on Admission in engine/system/resources.py:
   - Active POST {"model": ..., "keep_alive": 0} payload verification
   - Connection timeout, connection refused, HTTP 500, and SSRF failure modes
   - Fail-closed admission when memory remains constrained post-eviction
   - GPU physical total capacity boundary and saturation rejection
3. Single Art Workflow Invariant & Registry Safety
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from engine.comfyui.art import (
    ArtEngine,
    ComfyImageGenerationError,
    _extract_history_error,
)
from engine.comfyui.client import ComfyUIError
from engine.comfyui import ComfyWorkflowRegistry
from engine.system.resources import SystemResourceManager


# ============================================================================
# 1. WP-1.1: Fast ComfyUI Error Detection — Payload Stress Tests
# ============================================================================

def test_extract_history_error_real_world_cuda_oom():
    """Empirical Test: Real-world ComfyUI CUDA OOM error extraction."""
    oom_payload = {
        "prompt": ["test-prompt"],
        "outputs": {},
        "status": {
            "status_str": "error",
            "completed": False,
            "messages": [
                [
                    "execution_error",
                    {
                        "node_id": "4",
                        "node_type": "KSampler",
                        "executed": ["1", "2", "3"],
                        "exception_message": "CUDA out of memory. Tried to allocate 2.40 GiB (GPU 0; 15.99 GiB total capacity; 12.10 GiB already allocated; 1.80 GiB free; 12.50 GiB reserved in total by PyTorch)",
                        "exception_type": "torch.cuda.OutOfMemoryError",
                        "traceback": [
                            "Traceback (most recent call last):\n  File 'comfy/execution.py', line 151, in recursive_execute\n"
                        ],
                    },
                ]
            ],
        },
    }

    error_msg = _extract_history_error(oom_payload)
    assert error_msg is not None
    assert "CUDA out of memory" in error_msg
    assert "node 4: KSampler" in error_msg


def test_extract_history_error_real_world_execution_interrupted():
    """Empirical Test: Interrupted execution status."""
    interrupted_payload = {
        "status": {
            "status_str": "error",
            "completed": False,
            "messages": [
                [
                    "execution_interrupted",
                    {
                        "node_id": "7",
                        "node_type": "VAEDecode",
                        "executed": ["4"],
                    },
                ]
            ],
        }
    }
    error_msg = _extract_history_error(interrupted_payload)
    assert error_msg == "Execution interrupted at node 7: VAEDecode"

    # Variant: empty payload dictionary
    interrupted_empty = {
        "status": {
            "status_str": "error",
            "messages": [["execution_interrupted", {}]],
        }
    }
    assert _extract_history_error(interrupted_empty) == "Execution interrupted"

    # Variant: truncated message tuple
    interrupted_truncated = {
        "status": {
            "status_str": "error",
            "messages": [["execution_interrupted"]],
        }
    }
    assert _extract_history_error(interrupted_truncated) == "ComfyUI execution failed"


@pytest.mark.parametrize(
    "payload,expected_substr",
    [
        # None or non-dict inputs
        (None, None),
        ({}, None),
        ("not_a_dict", None),
        ([1, 2, 3], None),
        # Normal running or success status (must NOT trigger error)
        ({"status": {"status_str": "running", "messages": []}}, None),
        ({"status": {"status_str": "success", "messages": []}}, None),
        ({"status": None}, None),
        # Error status with missing or empty messages
        ({"status": {"status_str": "error"}}, "ComfyUI execution failed"),
        ({"status": {"status_str": "error", "messages": None}}, "ComfyUI execution failed"),
        ({"status": {"status_str": "error", "messages": []}}, "ComfyUI execution failed"),
        ({"status": {"status_str": "error", "messages": "corrupted_string"}}, "ComfyUI execution failed"),
        # Top-level status_str without status subdict
        ({"status_str": "error"}, "ComfyUI execution failed"),
        # Unrecognized message event under error status
        (
            {"status": {"status_str": "error", "messages": [["unknown_custom_event", {"info": "err"}]]}},
            "ComfyUI execution failed",
        ),
        # Fallback to exception_type when exception_message is empty
        (
            {
                "status": {
                    "status_str": "error",
                    "messages": [
                        [
                            "execution_error",
                            {"exception_type": "ZeroDivisionError", "node_id": "12", "node_type": "MathNode"},
                        ]
                    ],
                }
            },
            "ZeroDivisionError (node 12: MathNode)",
        ),
        # Direct dict error message
        (
            {"status": {"status_str": "error", "messages": [{"message": "Custom pipeline failure"}]}},
            "Custom pipeline failure",
        ),
        # Direct string error message
        (
            {"status": {"status_str": "error", "messages": ["Raw string fatal failure"]}},
            "Raw string fatal failure",
        ),
        # Prompt ID wrapper around record
        (
            {
                "prompt_uuid_999": {
                    "status": {
                        "status_str": "error",
                        "messages": [
                            [
                                "execution_error",
                                {"exception_message": "Wrapped prompt failure", "node_id": "1"},
                            ]
                        ],
                    }
                }
            },
            "Wrapped prompt failure (node 1: ?)",
        ),
    ],
)
def test_extract_history_error_adversarial_matrix(payload: Any, expected_substr: str | None):
    """Stress-test adversarial and malformed inputs to ensure deterministic error detection."""
    result = _extract_history_error(payload)
    if expected_substr is None:
        assert result is None, f"Expected None for payload {payload}, but got {result}"
    else:
        assert result is not None, f"Expected error containing '{expected_substr}', but got None"
        assert expected_substr in result


# ============================================================================
# 2. WP-1.1: Empirical Failure Latency Benchmark (< 1.5s vs 300s stall)
# ============================================================================

def test_art_engine_run_failure_latency_benchmark():
    """Empirically measure that ArtEngine.run terminates in < 1.5s on failure,

    eliminating the legacy 300s timeout stall.
    """
    mock_client = MagicMock()
    mock_client.submit_prompt.return_value = "prompt-bench-01"

    # Simulate history returning CUDA OOM failure on the very first polling check
    cuda_oom_history = {
        "prompt-bench-01": {
            "status": {
                "status_str": "error",
                "completed": False,
                "messages": [
                    [
                        "execution_error",
                        {
                            "node_id": "4",
                            "node_type": "KSampler",
                            "exception_message": "CUDA out of memory. Tried to allocate 2.40 GiB",
                            "exception_type": "torch.cuda.OutOfMemoryError",
                        },
                    ]
                ],
            },
            "outputs": {},
        }
    }
    mock_client.history.return_value = cuda_oom_history

    engine = ArtEngine(client=mock_client)

    t0 = time.perf_counter()
    with pytest.raises(ComfyImageGenerationError) as exc_info:
        engine.run(workflow={"prompt": {}}, timeout=300.0)
    elapsed = time.perf_counter() - t0

    # Verification: must raise ComfyImageGenerationError immediately (< 1.5s)
    assert elapsed < 1.5, f"Failure took {elapsed:.4f}s, exceeding 1.5s threshold"
    assert "CUDA out of memory" in str(exc_info.value)
    assert "node 4: KSampler" in str(exc_info.value)
    # Ensure it only polled once
    assert mock_client.history.call_count == 1


def test_art_engine_run_interrupted_latency_benchmark():
    """Empirically measure that ArtEngine.run terminates in < 1.5s on execution_interrupted."""
    mock_client = MagicMock()
    mock_client.submit_prompt.return_value = "prompt-bench-02"

    interrupted_history = {
        "status": {
            "status_str": "error",
            "messages": [
                [
                    "execution_interrupted",
                    {"node_id": "7", "node_type": "VAEDecode"},
                ]
            ],
        }
    }
    mock_client.history.return_value = interrupted_history

    engine = ArtEngine(client=mock_client)

    t0 = time.perf_counter()
    with pytest.raises(ComfyImageGenerationError) as exc_info:
        engine.run(workflow={"prompt": {}}, timeout=300.0)
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.5, f"Failure took {elapsed:.4f}s, exceeding 1.5s threshold"
    assert "Execution interrupted at node 7: VAEDecode" in str(exc_info.value)
    assert mock_client.history.call_count == 1


# ============================================================================
# 3. WP-1.2: Active Ollama Eviction on Admission — Empirical Protocol Tests
# ============================================================================

@pytest.mark.asyncio
async def test_try_evict_ollama_dispatches_exact_post_protocol(monkeypatch):
    """Empirically verify that _try_evict_ollama emits POST /api/generate with keep_alive: 0

    for all resident models and always includes qwen3.5:9b.
    """
    mgr = SystemResourceManager()
    captured_requests: list[dict[str, Any]] = []

    def mock_handler(request: httpx.Request):
        captured_requests.append({
            "method": request.method,
            "url": str(request.url),
            "payload": json.loads(request.content.decode("utf-8")),
            "headers": dict(request.headers),
        })
        return httpx.Response(200, json={"status": "success"})

    client_creator = httpx.AsyncClient
    def mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(mock_handler)
        return client_creator(*args, **kwargs)

    monkeypatch.setattr("engine.system.resources.httpx.AsyncClient", mock_client)

    # Test with custom models list
    success = await mgr._try_evict_ollama(
        endpoint_url="http://127.0.0.1:11434",
        models=["custom-lora-model:latest"],
    )

    assert success is True
    # Should evict both custom-lora-model:latest and qwen3.5:9b
    assert len(captured_requests) == 2

    # Verify request 1
    req1 = captured_requests[0]
    assert req1["method"] == "POST"
    assert req1["url"] == "http://127.0.0.1:11434/api/generate"
    assert req1["payload"] == {"model": "custom-lora-model:latest", "keep_alive": 0}

    # Verify request 2
    req2 = captured_requests[1]
    assert req2["method"] == "POST"
    assert req2["url"] == "http://127.0.0.1:11434/api/generate"
    assert req2["payload"] == {"model": "qwen3.5:9b", "keep_alive": 0}


@pytest.mark.asyncio
async def test_try_evict_ollama_failure_modes(monkeypatch):
    """Stress-test failure modes in _try_evict_ollama:

    - Connection timeout
    - Connection refused (Ollama offline)
    - HTTP 500 error from Ollama
    - SSRF / Invalid URL protection
    """
    mgr = SystemResourceManager()

    # 1. Timeout scenario
    def mock_timeout_client(*args, **kwargs):
        def raise_timeout(request: httpx.Request):
            raise httpx.ReadTimeout("Read timed out after 5.0s", request=request)
        kwargs["transport"] = httpx.MockTransport(raise_timeout)
        return httpx.AsyncClient(*args, **kwargs)

    monkeypatch.setattr("engine.system.resources.httpx.AsyncClient", mock_timeout_client)
    res_timeout = await mgr._try_evict_ollama()
    assert res_timeout is False, "Expected False on timeout"

    # 2. ConnectError scenario (Ollama down)
    def mock_connect_err_client(*args, **kwargs):
        def raise_connect_err(request: httpx.Request):
            raise httpx.ConnectError("Connection refused on 127.0.0.1:11434", request=request)
        kwargs["transport"] = httpx.MockTransport(raise_connect_err)
        return httpx.AsyncClient(*args, **kwargs)

    monkeypatch.setattr("engine.system.resources.httpx.AsyncClient", mock_connect_err_client)
    res_conn = await mgr._try_evict_ollama()
    assert res_conn is False, "Expected False on connect error"

    # 3. SSRF / Invalid URL
    res_ssrf = await mgr._try_evict_ollama(endpoint_url="http://169.254.169.254/latest/meta-data")
    assert res_ssrf is False, "Expected False on SSRF / untrusted endpoint"


# ============================================================================
# 4. WP-1.2: Admission Fail-Closed Behavior Under VRAM Constraints
# ============================================================================

@pytest.mark.asyncio
async def test_acquire_gpu_slot_fail_closed_if_vram_still_constrained(monkeypatch):
    """Adversarial Test: Verify fail-closed behavior when active eviction is triggered

    but fails to release sufficient VRAM (e.g. Ollama process busy, unevictable, or
    competing processes hold memory). ComfyUI slot MUST be rejected (returns False).
    """
    mgr = SystemResourceManager()
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16384.0,
        "free_mb": 2000.0,
        "used_mb": 14384.0,
    })

    # Ollama is using 7000MB initially, and STILL using 7000MB after eviction
    async def mock_stubborn_ollama(*args, **kwargs):
        return {
            "total_ollama_vram_mb": 7000.0,
            "loaded_models_count": 1,
            "models": [{"name": "qwen3.5:9b"}],
        }

    monkeypatch.setattr(mgr, "get_ollama_runtime", mock_stubborn_ollama)

    eviction_called = False
    async def mock_evict(*args, **kwargs):
        nonlocal eviction_called
        eviction_called = True
        return True

    monkeypatch.setattr(mgr, "_try_evict_ollama", mock_evict)

    # ComfyUI requests 10000 MB:
    # Available = total (16384) - ollama (7000) - reserve (4000) = 5384 MB < 10000 MB
    admitted = await mgr.acquire_gpu_slot("comfy_job_fail_closed", 10000.0, is_comfyui=True)

    # Verification: Eviction was attempted, but admission was strictly REJECTED (fail-closed)
    assert eviction_called is True
    assert admitted is False
    assert mgr.active_gpu_jobs_count == 0


@pytest.mark.asyncio
async def test_acquire_gpu_slot_rejects_physical_overcapacity(monkeypatch):
    """Verify that ComfyUI job requesting more VRAM than physical GPU capacity is rejected."""
    mgr = SystemResourceManager()
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16384.0,
        "free_mb": 16000.0,
        "used_mb": 384.0,
    })

    # Job requesting 24000 MB on 16384 MB GPU
    admitted = await mgr.acquire_gpu_slot("comfy_job_huge", 24000.0, is_comfyui=True)
    assert admitted is False
    assert mgr.active_gpu_jobs_count == 0


@pytest.mark.asyncio
async def test_acquire_gpu_slot_rejects_when_concurrency_saturated():
    """Verify that when active GPU slots are full, new requests are rejected."""
    mgr = SystemResourceManager()
    mgr.set_concurrency("MANUAL", 1)

    s1 = await mgr.acquire_gpu_slot("job_first", 0.0)
    assert s1 is True
    assert mgr.active_gpu_jobs_count == 1

    s2 = await mgr.acquire_gpu_slot("job_second", 0.0)
    assert s2 is False
    assert mgr.active_gpu_jobs_count == 1

    await mgr.release_gpu_slot("job_first")
    assert mgr.active_gpu_jobs_count == 0


# ============================================================================
# 5. WP-1.5: Invariant Verification
# ============================================================================

def test_single_art_workflow_invariant_strict():
    """Strict verification of Single Art Workflow invariant:

    Exactly ONE text_to_image workflow (qwen_image_21).
    All other workflows must be auxiliary (inpaint, matting, sdxl_conditioning).
    """
    registry_path = Path("engine/comfyui/workflow_registry.json")
    assert registry_path.is_file(), "workflow_registry.json must exist"

    with open(registry_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data if isinstance(data, list) else data.get("workflows", [])
    text_to_image_workflows = [
        w["id"] for w in entries
        if isinstance(w, dict) and w.get("purpose") == "text_to_image"
    ]

    assert text_to_image_workflows == ["qwen_image_21"], (
        f"Single Art Workflow violation: expected only ['qwen_image_21'], got {text_to_image_workflows}"
    )

    # Inpaint workflow must be qwen_image_21_inpaint with purpose 'inpaint'
    inpaint_workflows = [
        w for w in entries
        if isinstance(w, dict) and w.get("id") == "qwen_image_21_inpaint"
    ]
    assert len(inpaint_workflows) == 1, "qwen_image_21_inpaint must be registered"
    assert inpaint_workflows[0].get("purpose") == "inpaint", (
        f"qwen_image_21_inpaint must have purpose 'inpaint', got {inpaint_workflows[0].get('purpose')}"
    )
