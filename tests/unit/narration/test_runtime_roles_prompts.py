import pytest

from engine.config.settings import settings
from engine.narration.runtime import prompts
from engine.narration.runtime.prompts import PromptAsset, load_prompt
from engine.narration.runtime.roles import load_roles


def test_default_roles_match_spec():
    roles = load_roles()
    assert roles["vision"].temperature == 0.1 and roles["vision"].concurrency == 3
    assert roles["writer"].temperature == 0.7 and roles["writer"].top_p == 0.9
    assert roles["judge"].temperature == 0.0
    assert {r.model for r in roles.values()} == {"qwen3.5:9b"}


def test_user_override_replaces_one_role(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "narration_models.yaml").write_text(
        'roles:\n  judge: {model: "gemma3:9b", temperature: 0.0, max_tokens: 512}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    roles = load_roles()
    assert roles["judge"].model == "gemma3:9b"
    assert roles["vision"].model == "qwen3.5:9b"


def test_missing_required_role_raises(tmp_path):
    f = tmp_path / "m.yaml"
    f.write_text(
        'roles:\n  vision: {model: "m", temperature: 0.1, max_tokens: 10}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="planner"):
        load_roles(f)


def test_prompt_render_and_hash(tmp_path, monkeypatch):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "v1.md").write_text('Panel $n {"a": 1}', encoding="utf-8")
    monkeypatch.setattr(prompts, "PROMPTS_ROOT", tmp_path)
    p = load_prompt("x")
    assert p.render(n="7") == 'Panel 7 {"a": 1}'
    assert len(p.sha256) == 64


def test_render_missing_variable_raises():
    with pytest.raises(KeyError):
        PromptAsset(step="s", version="v1", text="$a $b", sha256="0" * 64).render(a="1")
