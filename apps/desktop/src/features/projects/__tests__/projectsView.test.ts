import test from "node:test";
import assert from "node:assert/strict";
import type { PipelineStage, Project } from "@panelflow/shared-types";
import { filterProjects, groupBySeries, projectInitials, stageLabel } from "../projectsView";
import { loadFavorites, saveFavorites, toggleFavorite } from "../favorites";

const p = (title: string, over: Partial<Project> = {}) => ({ id: title, title, updated_at: "2026-11-01", ...over } as Project);

// Ported from the old components/dashboard/__tests__/groupBySeries.test.ts, which used vitest (not installed) and never ran.
test("groupBySeries groups chapters of one series in chapter order and leaves singles out", () => {
  const { groups, singles } = groupBySeries([
    p("Magic Emperor - Chapter 928 - B - ManhuaPlus"),
    p("Tales Of Demons And Gods - Chapter 536.1 - X"),
    p("Magic Emperor - Chapter 927 - A - ManhuaPlus"),
    p("Standalone"),
  ]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].series, "Magic Emperor");
  assert.deepEqual(groups[0].projects.map((x) => x.title), ["Magic Emperor - Chapter 927 - A - ManhuaPlus", "Magic Emperor - Chapter 928 - B - ManhuaPlus"]);
  assert.deepEqual(singles.map((x) => x.title), ["Tales Of Demons And Gods - Chapter 536.1 - X", "Standalone"]);
});

const projects = [
  p("The Regressed Son Of A Duke", { id: "a", updated_at: "2026-11-02" }),
  p("Magic Emperor", { id: "b", updated_at: "2026-11-06" }),
  p("Moon Tales", { id: "c", updated_at: "2026-11-04" }),
];
const ids = (list: Project[]) => list.map((x) => x.id);
const base = { query: "", filter: "all" as const, favorites: {}, needsYou: new Set<string>() };

test("filterProjects matches the title case-insensitively and lists the newest update first", () => {
  assert.deepEqual(ids(filterProjects(projects, base)), ["b", "c", "a"]);
  assert.deepEqual(ids(filterProjects(projects, { ...base, query: "DUKE" })), ["a"]);
  assert.deepEqual(ids(filterProjects(projects, { ...base, query: "  moon " })), ["c"]);
  assert.deepEqual(filterProjects(projects, { ...base, query: "zzz" }), []);
});

test("filterProjects keeps only starred projects or only those that need you", () => {
  assert.deepEqual(ids(filterProjects(projects, { ...base, filter: "favorites", favorites: { c: true, a: false } })), ["c"]);
  assert.deepEqual(ids(filterProjects(projects, { ...base, filter: "needs-you", needsYou: new Set(["a", "b"]) })), ["b", "a"]);
});

test("filterProjects does not reorder its input", () => {
  const before = ids(projects);
  filterProjects(projects, base);
  assert.deepEqual(ids(projects), before);
});

test("projectInitials takes the first letters of the first two words", () => {
  assert.equal(projectInitials("Regressed Son Of A Duke"), "RS");
  assert.equal(projectInitials("Moon"), "MO");
  assert.equal(projectInitials("  magic   emperor "), "ME");
  assert.equal(projectInitials(""), "?");
});

test("stageLabel has a plain-language label for every pipeline stage", () => {
  const stages: PipelineStage[] = ["NEW", "RIGHTS_APPROVED", "ACQUIRED", "NORMALIZED", "PANELS_DETECTED", "OCR_COMPLETE", "OCR_APPROVED", "STORY_ANALYZED", "STORY_APPROVED", "SCRIPT_GENERATED", "SCRIPT_APPROVED", "VOICE_GENERATED", "AUDIO_APPROVED", "SHOT_PLAN_GENERATED", "MOTION_APPROVED", "RENDERED", "QA_APPROVED", "EXPORTED"];
  for (const stage of stages) assert.ok(stageLabel(stage).length > 3 && !stageLabel(stage).includes("_"), stage);
  assert.equal(stageLabel("OCR_COMPLETE"), "OCR ready for review");
  assert.equal(stageLabel("QA_APPROVED"), "Ready to upload");
});

test("toggleFavorite flips a project and leaves its input alone", () => {
  const before = { a: true };
  assert.deepEqual(toggleFavorite(before, "a"), { a: false });
  assert.deepEqual(toggleFavorite(before, "b"), { a: true, b: true });
  assert.deepEqual(before, { a: true });
});

test("favourites round-trip through storage under the existing key and survive bad data", () => {
  const store = new Map<string, string>();
  const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };
  saveFavorites(storage, { a: true });
  assert.equal(store.get("panelflow_project_favorites"), '{"a":true}');
  assert.deepEqual(loadFavorites(storage), { a: true });
  store.set("panelflow_project_favorites", "not json");
  assert.deepEqual(loadFavorites(storage), {});
  assert.deepEqual(loadFavorites({ getItem: () => { throw new Error("blocked"); } }), {});
  assert.doesNotThrow(() => saveFavorites({ setItem: () => { throw new Error("quota"); } }, { a: true }));
});
