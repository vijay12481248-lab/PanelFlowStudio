import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from engine.chronoflow.pipeline import ChronoFlowPipeline


def test_compile_h3_prompt():
    pipeline = ChronoFlowPipeline()
    compiled = pipeline.compile_h3_prompt(
        detailed_description="Maya Voss breaches the archway.",
        subject_definitions="Maya Voss: Operative in armored suit.",
        summary="Scene 1: Establishing Shot",
        retention_analysis="Silhouette and armor conduits strictly preserved.",
        soundscape="Subtle wind howl and suit airflow.",
        music="Deep cosmic sub-bass drone.",
    )

    assert "subject_definitions:\nMaya Voss: Operative in armored suit." in compiled
    assert "summary:\nScene 1: Establishing Shot" in compiled
    assert "retention_analysis:\nSilhouette and armor conduits strictly preserved." in compiled
    assert "detailed_description:\nMaya Voss breaches the archway." in compiled
    assert "overall_soundscape:\nSubtle wind howl and suit airflow." in compiled
    assert "non_diegetic_music:\nDeep cosmic sub-bass drone." in compiled


def test_build_h3_prompt_sliding_window():
    pipeline = ChronoFlowPipeline()
    graph = pipeline.build_h3_prompt(
        prompt="Cinematic shot of survivor running",
        width=1344,
        height=768,
        length=124,
        steps=4,
        lora_name="minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
        workflow_mode="sliding_window",
        first_frame_filename="tail_frame_1.png",
        seed=42,
    )

    assert "1" in graph
    assert graph["1"]["class_type"] == "UNETLoader"
    assert graph["1"]["inputs"]["unet_name"] == "minimax_h3_fl2va_pruned_int8_convrot.safetensors"

    assert "7" in graph
    assert graph["7"]["class_type"] == "MiniMaxH3ImageToVideo"
    assert "load_first" in graph
    assert graph["load_first"]["inputs"]["image"] == "tail_frame_1.png"
    assert graph["11"]["inputs"]["noise_seed"] == 42


def test_build_h3_prompt_flf2v():
    pipeline = ChronoFlowPipeline()
    graph = pipeline.build_h3_prompt(
        prompt="Survivor leaping between roofs",
        width=1344,
        height=768,
        length=124,
        steps=4,
        lora_name="minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
        workflow_mode="flf2v",
        first_frame_filename="start.png",
        last_frame_filename="end.png",
        seed=100,
    )

    assert "load_first" in graph
    assert graph["load_first"]["inputs"]["image"] == "start.png"
    assert "load_last" in graph
    assert graph["load_last"]["inputs"]["image"] == "end.png"


def test_build_h3_prompt_reference_locking():
    pipeline = ChronoFlowPipeline()
    refs = ["turnaround_front.png", "turnaround_side.png", "turnaround_back.png"]
    graph = pipeline.build_h3_prompt(
        prompt="Maya inspecting console",
        width=1344,
        height=768,
        length=124,
        steps=4,
        lora_name="minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors",
        workflow_mode="reference",
        ref_images=refs,
        seed=200,
    )

    assert graph["7"]["class_type"] == "MiniMaxH3ReferenceToVideo"
    assert "ref_img_1" in graph
    assert graph["ref_img_1"]["inputs"]["image"] == "turnaround_front.png"
    assert "ref_img_2" in graph
    assert graph["ref_img_2"]["inputs"]["image"] == "turnaround_side.png"
    assert "ref_img_3" in graph
    assert graph["ref_img_3"]["inputs"]["image"] == "turnaround_back.png"


def test_chronoflow_has_no_graphs_of_its_own_for_text_to_image():
    # one text-to-image workflow for all of PanelFlow: engine/comfyui/art.py
    assert not hasattr(ChronoFlowPipeline, "build_qwen_image_prompt")
    assert not hasattr(ChronoFlowPipeline, "build_flux_image_prompt")


def test_generate_art_image_uses_the_central_art_engine_and_saves_into_the_input_folder(tmp_path, monkeypatch):
    import asyncio

    from engine.chronoflow import pipeline as pl

    seen = []

    class FakeArt:
        def generate(self, prompt, negative, width, height, seed, prefix):
            seen.append((prompt, negative, width, height, seed, prefix))
            return type("Img", (), {"png": b"png-bytes"})()

    monkeypatch.setattr(pl, "ArtEngine", FakeArt)
    monkeypatch.setattr(pl, "COMFY_INPUT_DIR", tmp_path)
    name = asyncio.run(ChronoFlowPipeline().generate_art_image("a fox", "blurry", "1344", 768, 5))
    assert seen == [("a fox", "blurry", 1344, 768, 5, "chronoflow_art")]
    assert (tmp_path / name).read_bytes() == b"png-bytes" and name.startswith("art_") and name.endswith(".png")


def test_build_inpaint_prompt():
    pipeline = ChronoFlowPipeline()
    graph = pipeline.build_inpaint_prompt(
        image_filename="source.png",
        mask_filename="mask.png",
        prompt="glowing cyan visor",
        denoise=0.85,
        steps=4,
        seed=999,
    )

    assert graph["3"]["inputs"]["image"] == "source.png"
    assert graph["4"]["inputs"]["image"] == "mask.png"
    assert graph["6"]["class_type"] == "SetLatentNoiseMask"
    assert graph["9"]["class_type"] == "ImageCompositeMasked"


@patch("subprocess.run")
def test_extract_tail_frame(mock_run, tmp_path):
    pipeline = ChronoFlowPipeline()
    video_file = tmp_path / "test_chunk.mp4"
    video_file.write_bytes(b"fake_video")
    out_img = tmp_path / "tail.png"

    # Simulate success
    def fake_run(cmd, **kwargs):
        out_img.write_bytes(b"fake_image")
        mock_res = MagicMock()
        mock_res.returncode = 0
        return mock_res

    mock_run.side_effect = fake_run

    success = pipeline.extract_tail_frame(video_file, out_img)
    assert success is True
    assert out_img.exists()
