import assert from "node:assert/strict";
import test from "node:test";
import type { StoryEditorState, VideoScene } from "@panelflow/shared-types";
import { alignLinkedNarration, insertSceneTiming, packSceneTiming, reconcileSceneDurationEdit, resolveSceneTiming, sceneAtTime, sceneTimelineDuration, trimSceneTiming } from "../sceneTiming";

const scenes = (): VideoScene[] => [
  { id: "a", sequence: 1, title: "A", duration_sec: 6, start_time_sec: 0, layers: [] },
  { id: "b", sequence: 2, title: "B", duration_sec: 4, start_time_sec: 6, layers: [] },
];
const state = (): StoryEditorState => ({ scenes: scenes(), narration_clips: [], bgm_tracks: [] } as unknown as StoryEditorState);

test("missing Ripple flag preserves default ON contiguous trim behavior", () => {
  const result = trimSceneTiming(state(), "a", 4);
  assert.deepEqual(result.scenes.map(scene => scene.start_time_sec), [0, 4]);
  assert.equal(sceneTimelineDuration(result.scenes), 8);
});

test("legacy missing and stale starts are cumulative without closing explicit gaps", () => {
  const input = scenes();
  delete (input[0] as Partial<VideoScene>).start_time_sec;
  input[1].start_time_sec = 0;
  assert.deepEqual(resolveSceneTiming(input).map(scene => scene.start_time_sec), [0, 6]);
  input[1].start_time_sec = 9;
  assert.equal(sceneTimelineDuration(input), 13);
  assert.equal(sceneAtTime(input, 6), null);
  assert.equal(sceneAtTime(input, 8.99), null);
  assert.equal(sceneAtTime(input, 9)?.id, "b");
  assert.equal(sceneAtTime(input, 13), null);
  assert.deepEqual(packSceneTiming(input).map(scene => scene.start_time_sec), [0, 6]);
});

test("missing linked offset is inferred from old parent; floating audio stays absolute", () => {
  const previous = scenes();
  const next = packSceneTiming([{ ...previous[0], duration_sec: 4 }, previous[1]]);
  const clips = [
    { id: "linked", scene_id: "b", start_time_sec: 6.5, duration_sec: 1, text: "fixture" },
    { id: "floating", scene_id: "b", linked_to_scene: false, start_time_sec: 9, duration_sec: 1, text: "fixture" },
  ] as StoryEditorState["narration_clips"];
  const aligned = alignLinkedNarration(next, clips, previous);
  assert.equal(aligned[0].start_time_sec, 4.5);
  assert.equal(aligned[0].scene_offset_sec, 0.5);
  assert.equal(aligned[1], clips[1]);
});

test("OFF inspector repack is corrected to old anchors and growth is bounded", () => {
  const previous = state(); previous.ripple_edit = false;
  const next = { ...previous, scenes: packSceneTiming([{ ...previous.scenes[0], duration_sec: 8 }, previous.scenes[1]]) };
  const result = reconcileSceneDurationEdit(previous, next);
  assert.deepEqual(result.scenes.map(scene => [scene.start_time_sec, scene.duration_sec]), [[0, 6], [6, 4]]);
  assert.equal(reconcileSceneDurationEdit(previous, previous), previous);
});

test("OFF insert uses a large enough gap or appends without moving existing scenes", () => {
  const input = scenes(); input[0].duration_sec = 2;
  const added = { ...input[0], id: "new", duration_sec: 4 };
  assert.deepEqual(insertSceneTiming(input, added, 1, false).map(scene => [scene.id, scene.start_time_sec]), [["a", 0], ["new", 2], ["b", 6]]);
  added.duration_sec = 5;
  assert.deepEqual(insertSceneTiming(input, added, 1, false).map(scene => [scene.id, scene.start_time_sec]), [["a", 0], ["b", 6], ["new", 10]]);
});
