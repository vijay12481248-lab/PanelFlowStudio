"""Two vision judges with one answer shape: `qwen3.5:9b` through Ollama and Qwen3-VL 8B through ComfyUI's `TextGenerate` node.

Both are asked the same plain-text question (never the plan, so a judge cannot just agree with what it was told to expect) and their text is parsed the same
way. A judge never raises: an unreachable or rambling judge returns `ok=False`. The ComfyUI judge needs ComfyUI started with `--disable-dynamic-vram`
(measured: with it on, `TextGenerate` fails inside ComfyUI with `comfy_kitchen has no attribute memmove`).
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field

Camera = Literal["looks_up", "level", "looks_down", "tilted"]
Topic = Literal["camera", "people", "action"]
NUMBER_WORDS = {"zero": 0, "no": 0, "none": 0, "nobody": 0, "one": 1, "single": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10}
FILLER = {"the", "a", "an", "is", "are", "was", "his", "her", "their", "both", "person", "man", "woman"}
CAMERA_PATTERNS = (
    ("tilted", r"tilt|dutch|slant"),
    ("looks_up", r"looks_up|look\w*\s+up|from\s+below|upward|\bup\b|low[- ]angle"),
    ("looks_down", r"looks_down|look\w*\s+down|from\s+above|downward|\bdown\b|high[- ]angle|overhead|bird"),
    ("level", r"level|eye[- ]level|straight|even"),
)


class JudgeAnswer(BaseModel):
    judge: str
    ok: bool = False  # False when the judge was unreachable or its answer could not be read
    camera: Camera | None = None
    people: int | None = None
    actions: list[str] = Field(default_factory=list)  # one lowercase word per person, left to right
    evidence: str = ""
    raw: str = ""


def _field(text: str, name: str) -> str | None:
    m = re.search(rf"(?ims)^\s*{name}\s*:\s*(.*?)\s*(?=^\s*(?:CAMERA|PEOPLE|ACTIONS|EVIDENCE)\s*:|\Z)", text)
    return m.group(1).strip() if m else None


def _camera(value: str | None) -> str | None:
    if not value:
        return None
    best = None
    for name, pattern in CAMERA_PATTERNS:
        m = re.search(pattern, value.lower())
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


def _people(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"\d+", value)
    if m:
        return int(m.group())
    for word in re.findall(r"[a-z]+", value.lower()):
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word]
    return None


def _actions(value: str | None, states: list[str]) -> list[str]:
    if not value:
        return []
    cleaned = re.sub(r"(?im)\b(left|right|centre|center|middle)\s*:|\bperson\s*\d+\s*:|^\s*\d+[.)]\s*", "|", value)
    out = []
    for seg in re.split(r"[|;\n,.]", cleaned):
        words = [w for w in re.findall(r"[a-z]+", seg.lower()) if w not in FILLER]
        if not words:
            continue
        word = words[0]
        out.append(next((s for s in states if word == s or (len(word) >= 5 and word[:5] == s[:5])), word))
    return out


def parse_judge_text(text: str, judge: str, states: list[str]) -> JudgeAnswer:
    text = text or ""
    camera, people = _camera(_field(text, "CAMERA")), _people(_field(text, "PEOPLE"))
    actions = _actions(_field(text, "ACTIONS"), states)
    return JudgeAnswer(judge=judge, ok=camera is not None or people is not None or bool(actions), camera=camera, people=people,
                       actions=actions, evidence=_field(text, "EVIDENCE") or "", raw=text[:600])


def read_prompt(states: list[str]) -> str:
    """The first-round question: identical for every judge and blind to what anyone expects."""
    return ("Look at the picture and answer exactly in this format, nothing else:\n"
            "CAMERA: looks_up (the camera is below the people looking up at them) | level | looks_down (the camera is above, looking down) | tilted\n"
            "PEOPLE: <how many people are clearly visible, as a number>\n"
            f"ACTIONS: <for each person from the LEFT of the picture to the RIGHT, one word from {states} describing what their body is doing, separated by ;>\n"
            "EVIDENCE: <one short sentence naming what you can see that shows it>")


def reread_prompt(topic: Topic, index: int | None, other_value: str, other_evidence: str, states: list[str]) -> str:
    """The second-round question for ONE disputed point: it states the other reviewer's claim and asks for a fresh answer and what is visible, not for agreement."""
    ordinal = {0: "first", 1: "second", 2: "third"}.get(index or 0, f"number {(index or 0) + 1}")
    what = {"camera": "the camera angle (looks_up, level, looks_down or tilted)",
            "people": "how many people are clearly visible",
            "action": f"what the {ordinal} person from the left is doing with their body (one word from {states})"}[topic]
    line = {"camera": "CAMERA", "people": "PEOPLE", "action": "ACTIONS"}[topic]
    return (f"Another reviewer looked at this same picture and says about {what}: \"{other_value}\", because \"{other_evidence or 'no reason given'}\". "
            "Do not assume they are right, and do not assume you were. Look again at this one point only.\n"
            f"Answer in exactly two lines:\n{line}: <your answer>\nEVIDENCE: <what you can see in the picture that shows it>")


def item_value(answer: JudgeAnswer, topic: Topic, index: int | None = None, reread: bool = False) -> str | None:
    """The value of one item from an answer; a reread of an action holds just that one person's word."""
    if topic == "camera":
        return answer.camera
    if topic == "people":
        return None if answer.people is None else str(answer.people)
    if reread:
        return answer.actions[0] if answer.actions else None
    return answer.actions[index] if index is not None and index < len(answer.actions) else None


class Judge(Protocol):
    name: str

    async def read(self, image: Path | bytes, states: list[str]) -> JudgeAnswer: ...

    async def reread(self, image: Path | bytes, topic: Topic, index: int | None, other: JudgeAnswer, states: list[str]) -> JudgeAnswer: ...


class _Base:
    name = "judge"

    async def _ask(self, image, prompt: str) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    async def _answer(self, image, prompt: str, states: list[str]) -> JudgeAnswer:
        try:
            return parse_judge_text(await self._ask(image, prompt), self.name, states)
        except Exception as exc:  # a judge never raises: the cross-check treats it as absent
            return JudgeAnswer(judge=self.name, ok=False, raw=f"error: {type(exc).__name__}: {exc}"[:300])

    async def read(self, image, states):
        return await self._answer(image, read_prompt(states), states)

    async def reread(self, image, topic, index, other, states):
        value = item_value(other, topic, index)
        return await self._answer(image, reread_prompt(topic, index, value or "unknown", other.evidence, states), states)


class OllamaJudge(_Base):
    def __init__(self, provider, name: str = "qwen3.5:9b"):
        self.provider, self.name = provider, name

    async def _ask(self, image, prompt: str) -> str:
        return str(await self.provider.analyze_vision(image, prompt, max_tokens=300, temperature=0.0))


class ComfyJudge(_Base):
    def __init__(self, client, name: str = "qwen3-vl-8b", clip_name: str = "qwen3vl_8b_int8_convrot.safetensors", timeout_s: float = 120.0, poll_s: float = 1.0):
        self.client, self.name, self.clip_name, self.timeout_s, self.poll_s = client, name, clip_name, timeout_s, poll_s

    def build_graph(self, image_name: str, prompt: str) -> dict:
        return {
            "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
            "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": self.clip_name, "type": "qwen_image", "device": "default"}},
            "3": {"class_type": "TextGenerate", "inputs": {"clip": ["2", 0], "prompt": prompt, "max_length": 200, "sampling_mode": "off", "image": ["1", 0], "thinking": False}},
            "4": {"class_type": "PreviewAny", "inputs": {"source": ["3", 0]}},
        }

    def _run_sync(self, image, prompt: str) -> str:
        data = image if isinstance(image, bytes) else Path(image).read_bytes()
        pid = self.client.submit_prompt(self.build_graph(self.client.upload_image_bytes(data), prompt))
        t0 = time.monotonic()
        while True:
            entry = self.client.history(pid).get(pid)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError("ComfyUI execution failed")
                text = entry.get("outputs", {}).get("4", {}).get("text")
                if text:
                    return str(text[0])
                if status.get("completed"):
                    raise RuntimeError("ComfyUI finished without a text output")
            if time.monotonic() - t0 > self.timeout_s:
                raise TimeoutError("ComfyUI text generation timed out")
            time.sleep(self.poll_s)

    async def _ask(self, image, prompt: str) -> str:
        return await asyncio.to_thread(self._run_sync, image, prompt)


async def available_judges(provider, client) -> list[Judge]:
    """The Ollama judge always; the ComfyUI judge only when ComfyUI has the `TextGenerate` node and the Qwen3-VL file. Never raises."""
    judges: list[Judge] = [OllamaJudge(provider)]
    try:
        catalog = await asyncio.to_thread(client.node_catalog)
        models = await asyncio.to_thread(client.discover_models)
        candidate = ComfyJudge(client)
        if "TextGenerate" in catalog and candidate.clip_name in models.get("text_encoders", []):
            judges.append(candidate)
    except Exception:
        pass
    return judges


def default_judges(provider, client=None) -> list[Judge]:
    """The judges the Scene Director uses (blocking): both when available (the cross-check passed its gate, see docs/SCENE_DIRECTOR.md), only the first with SCENE_CROSSCHECK=0."""
    if client is None:
        from engine.comfyui.client import ComfyUIClient

        client = ComfyUIClient()
    found = asyncio.run(available_judges(provider, client))
    return found[:1] if os.environ.get("SCENE_CROSSCHECK") == "0" else found
