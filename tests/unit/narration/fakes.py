"""Test doubles for the narration model client."""
from __future__ import annotations


class FakeModelClient:
    def __init__(self, responses: dict[str, list], models: dict[str, str] | None = None,
                 params: dict | None = None):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.models = models or {}
        self.params = params or {}
        self.calls: list[tuple] = []

    def model_for(self, role: str) -> str:
        return self.models.get(role, "qwen3.5:9b")

    def params_for(self, role: str) -> dict:
        return self.params

    async def structured(self, role, prompt, schema, image=None, system=None):
        self.calls.append((role, prompt, image))
        queue = self.responses.get(role)
        if not queue:
            raise AssertionError(f"no queued response for role '{role}'")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(prompt) if callable(item) else item


class RecordingUnloader:
    def __init__(self):
        self.unloaded: list[str] = []

    async def __call__(self, model: str) -> None:
        self.unloaded.append(model)


def make_chapter_inputs(tmp_path, n_panels: int, ocr: dict[int, list[str]]):
    """Tiny-PNG ChapterInputs; ocr maps 1-based panel number to its region texts."""
    from PIL import Image

    from engine.narration.inputs import ChapterInputs, OcrRegionInput, PanelInput

    panels = []
    for k in range(1, n_panels + 1):
        path = tmp_path / f"p{k}.png"
        Image.new("RGB", (4, 4), "white").save(path)
        regions = [OcrRegionInput(f"p{k}-r{j}", t, "SPEECH") for j, t in enumerate(ocr.get(k, []), start=1)]
        panels.append(PanelInput(f"p{k}", k, path, regions))
    return ChapterInputs("proj-test", "test-series", panels)