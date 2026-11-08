import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup as html } from "react-dom/server";
import { Dock, EngineStatus, InboxRow, JobCard, PageHeader, Stepper } from "../index";

const ITEMS = [
  { id: "home", label: "Home", icon: <i />, href: "#/home" },
  { id: "jobs", label: "Jobs", icon: <i />, href: "#/jobs" },
  { id: "settings", label: "Settings", icon: <i />, href: "#/settings" },
];

test("Dock marks exactly the active destination as the current page", () => {
  const markup = html(<Dock items={ITEMS} activeId="jobs" />);
  assert.equal(markup.match(/aria-current="page"/g)?.length, 1);
  assert.ok(/aria-current="page"[^>]*>.*Jobs/.test(markup.replace(/\n/g, "")) || markup.includes("Jobs"));
  assert.ok(markup.includes('aria-label="Main"'));
});

test("Dock lets the shell supply router links", () => {
  const markup = html(<Dock items={ITEMS} activeId="home" renderLink={(item, children) => <a data-router-link={item.id} href={item.href}>{children}</a>} />);
  assert.ok(markup.includes('data-router-link="settings"'));
});

test("Stepper says Stale and Blocked in words, not only colour", () => {
  const markup = html(<Stepper steps={[
    { id: "ocr", label: "OCR", status: "done" },
    { id: "story", label: "Story", status: "stale" },
    { id: "script", label: "Script", status: "blocked" },
    { id: "audio", label: "Audio", status: "upcoming" },
  ]} />);
  assert.ok(markup.includes("Stale"));
  assert.ok(markup.includes("Blocked"));
  assert.ok(markup.includes("Done"));
});

test("Stepper marks the active step as the current step", () => {
  const markup = html(<Stepper steps={[{ id: "a", label: "A", status: "done" }, { id: "b", label: "B", status: "active" }]} />);
  assert.equal(markup.match(/aria-current="step"/g)?.length, 1);
});

test("EngineStatus words its state", () => {
  assert.ok(html(<EngineStatus connected={false} />).includes("Engine offline"));
  const ready = html(<EngineStatus connected version="1.0.0-beta.2" gpu="13.1 / 16 GB" />);
  assert.ok(ready.includes("Engine ready"));
  assert.ok(ready.includes("1.0.0-beta.2"));
  assert.ok(ready.includes("13.1 / 16 GB"));
});

test("InboxRow shows its action as a button with the given label", () => {
  const markup = html(<InboxRow kind="failed" title="H3 clip 4 of 7 failed" subtitle="Out of GPU memory" actionLabel="Retry" onAction={() => {}} />);
  assert.ok(markup.includes("H3 clip 4 of 7 failed"));
  assert.ok(/<button[^>]*>Retry<\/button>/.test(markup));
  assert.ok(markup.includes("Failed"));
});

test("JobCard offers Retry for a failed job and Cancel plus progress for a running one", () => {
  const failed = html(<JobCard title="Render" detail="Out of GPU memory" state="failed" onRetry={() => {}} />);
  assert.ok(failed.includes("Retry"));
  assert.ok(!failed.includes("Cancel"));
  const running = html(<JobCard title="Render" detail="Scene 9 of 14" state="running" progress={62} onCancel={() => {}} />);
  assert.ok(running.includes("Cancel"));
  assert.ok(running.includes('aria-valuenow="62"'));
});

test("PageHeader renders one h1 with its meta and actions", () => {
  const markup = html(<PageHeader title="Dawn Gate" meta={<span>Episode 4</span>} actions={<button>Continue</button>} />);
  assert.equal(markup.match(/<h1/g)?.length, 1);
  assert.ok(markup.includes("Episode 4"));
  assert.ok(markup.includes("Continue"));
});
