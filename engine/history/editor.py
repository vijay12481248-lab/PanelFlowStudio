"""PanelFlow's editor Memento strategy. No filesystem effects or internal commits."""
from copy import deepcopy
import re
from urllib.parse import urlsplit, parse_qsl, urlencode

from engine.history.contracts import HistoryFault

TRANSIENT = {"is_playing", "playhead_sec", "selected_object", "zoom_level", "clipboard_animation", "panel_review_sync", "panels_stale", "panel_sync_required"}
PERSISTED_UI = {"zoom_level"}
SECRET_KEYS = {"api_key", "access_token", "engine_token", "authorization", "x-panelflow-token"}
URL_SECRET_KEYS = {"token", "pf-token", "engine_token", "engine-token", "x-panelflow-token"}


def sanitize(value):
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        if any(str(key).lower() in SECRET_KEYS for key in value):
            raise HistoryFault("VALIDATION", "Credentials are not permitted in editor history", 422)
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, str):
        try:
            url = urlsplit(value)
            local = not url.netloc or url.hostname in {"127.0.0.1", "localhost", "::1"}
            if local and url.path.startswith("/api/projects/"):
                path = re.sub(r";pf-token=[^/;]*$", "", url.path)
                query = urlencode([(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True) if k.lower() not in URL_SECRET_KEYS])
                return path + ("?" + query if query else "")
        except ValueError:
            pass
    return value


def document(state):
    if state is None:
        return None
    result = {key: value for key, value in sanitize(deepcopy(state)).items() if key not in TRANSIENT}
    result.setdefault("mode", "simple")
    return result


class EditorStateStrategy:
    def prepare(self, db, project, input):
        state = input.get("state") if isinstance(input, dict) else None
        if not isinstance(state, dict) or state.get("project_id", project.id) != project.id or not isinstance(state.get("scenes"), list):
            raise HistoryFault("VALIDATION", "Invalid editor state or project scope", 422)
        if any(not isinstance(scene, dict) or not isinstance(scene.get("layers", []), list) for scene in state["scenes"]):
            raise HistoryFault("VALIDATION", "Invalid scene layers", 422)
        clean = sanitize(deepcopy({**state, "project_id": project.id}))
        before = document((project.settings or {}).get("story_editor_state"))
        after = document(clean)
        # Saved UI preferences must survive a normal save, but must not turn a
        # viewport-only adjustment into an undoable document edit.
        forward_ui = {key: clean[key] for key in PERSISTED_UI if key in clean}
        return None if before == after else {"before": before, "after": after, "forward_ui": forward_ui}

    def validate(self, payload):
        if not isinstance(payload, dict) or set(payload) not in ({"before", "after"}, {"before", "after", "forward_ui"}):
            return False
        if not all(item is None or (isinstance(item, dict) and isinstance(item.get("scenes"), list)) for item in (payload["before"], payload["after"])):
            return False
        return "forward_ui" not in payload or (isinstance(payload["forward_ui"], dict) and set(payload["forward_ui"]) <= PERSISTED_UI)

    def apply(self, db, project, payload, *, forward):
        state = deepcopy(payload["after" if forward else "before"])
        settings = dict(project.settings or {})
        if state is None:
            settings.pop("story_editor_state", None)
        else:
            if state.get("project_id") != project.id:
                raise HistoryFault("VALIDATION", "Stored editor scope does not match project", 422)
            previous = settings.get("story_editor_state") or {}
            ui = payload.get("forward_ui", {}) if forward else previous
            settings["story_editor_state"] = {
                **state, "is_playing": False, "playhead_sec": 0, "selected_object": None,
                "zoom_level": ui.get("zoom_level", previous.get("zoom_level", 1)),
                "mode": state.get("mode", "simple"),
            }
        project.settings = settings
        db.add(project)
