import test from "node:test";
import assert from "node:assert/strict";
import { buildCommands } from "../commands";
import { paths, stageForProject } from "../routes";

const projects = [
  { id: "p1", title: "Magic Emperor", current_stage: "OCR_COMPLETE" as const, settings: {}, source_type: "MANGA" as const },
  { id: "p2", title: "Moon Tales", current_stage: "NEW" as const, settings: { workflow_type: "chronoflow" }, source_type: "MANGA" as const },
];

test("every destination in the dock and every studio and settings section has a Go to command", () => {
  const targets = buildCommands({ projects: [] }).map((c) => c.to);
  const expected = [
    paths.home(), paths.projects(), paths.create(), paths.create("new"), paths.create("stories"), paths.create("anime"),
    paths.create("chronoflow"), paths.create("image"), paths.jobs(), paths.library(),
    ...(["engine", "models", "providers", "youtube", "diagnostics"] as const).map((s) => paths.settings(s)),
  ];
  for (const path of expected) assert.ok(targets.includes(path), `missing command for ${path}`);
});

test("a project command opens the stage the project is at", () => {
  const command = buildCommands({ projects }).find((c) => c.label === "Open Magic Emperor");
  assert.equal(command?.to, paths.stage("p1", stageForProject(projects[0])));
  assert.equal(command?.group, "Projects");
});

test("a ChronoFlow project opens ChronoFlow, never a pipeline stage", () => {
  const command = buildCommands({ projects }).find((c) => c.label === "Open Moon Tales");
  assert.equal(command?.to, paths.chronoflow({ projectId: "p2" }));
});

test("command ids are unique and every label starts with a verb", () => {
  const commands = buildCommands({ projects });
  assert.equal(new Set(commands.map((c) => c.id)).size, commands.length);
  for (const command of commands) assert.match(command.label, /^(Open|Create|Start)\b/, command.label);
});

test("labels use sentence case (only the first word and project titles are capitalised)", () => {
  const generic = buildCommands({ projects: [] });
  for (const command of generic) {
    const rest = command.label.split(" ").slice(1).join(" ");
    assert.ok(!/\b[A-Z][a-z]+\b/.test(rest.replace(/ChronoFlow|Original Stories/g, "")), command.label);
  }
});
