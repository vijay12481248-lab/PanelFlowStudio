import pytest
from pydantic import ValidationError

from engine.config.settings import settings
from engine.narration.runtime import prompts
from engine.narration.runtime.prompts import PromptAsset, load_prompt
from engine.narration.runtime.roles import RoleConfig, load_roles


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


def test_zero_concurrency_rejected():
    with pytest.raises(ValidationError):
        RoleConfig(model="m", temperature=0, max_tokens=1, concurrency=0)


def test_partial_override_merges_over_defaults(tmp_path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "narration_models.yaml").write_text('roles:\n  writer: {model: "gemma3:9b"}\n', encoding="utf-8")
    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    writer = load_roles()["writer"]
    assert writer.model == "gemma3:9b" and writer.temperature == 0.7 and writer.top_p == 0.9


def test_crlf_and_lf_prompts_hash_and_render_the_same(tmp_path, monkeypatch):
    for name, raw in (("a", b"Line $n\r\nnext\r\n"), ("b", b"Line $n\nnext\n")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "v1.md").write_bytes(raw)
    monkeypatch.setattr(prompts, "PROMPTS_ROOT", tmp_path)
    a, b = load_prompt("a"), load_prompt("b")
    assert a.sha256 == b.sha256 and a.text == b.text and "\r" not in a.text