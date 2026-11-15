import test from "node:test";
import assert from "node:assert/strict";
import { engineReason, refusal } from "../engineReason";

test("a short plain engine message is kept as the reason", () => {
  assert.equal(engineReason(new Error("  Project must have at least one ready page.  ")), "Project must have at least one ready page.");
  assert.equal(engineReason({ message: "Pages are not acquired yet" }), "Pages are not acquired yet");
});

test("messages that look like exceptions, paths or network noise are hidden", () => {
  for (const message of [
    "ENOENT at C:\\engine\\secret.py line 9",
    "Traceback (most recent call last): boom",
    "open /home/user/app/data.db failed",
    "Failed to fetch",
    "TypeError: NetworkError when attempting to fetch resource.",
    "x".repeat(300),
    "",
  ]) assert.equal(engineReason(new Error(message)), null, message.slice(0, 30));
  assert.equal(engineReason(undefined), null);
  assert.equal(engineReason("plain string"), null, "only error-like objects");
});

test("refusal joins a headline with the reason, or with the fallback advice", () => {
  assert.equal(refusal("Couldn't confirm the pages.", new Error("No pages are ready.")), "Couldn't confirm the pages. No pages are ready.");
  assert.equal(refusal("Couldn't confirm the pages.", new Error("Failed to fetch")), "Couldn't confirm the pages. Check that the engine is running, then try again.");
  assert.equal(refusal("Motion can't be approved yet.", new Error("Failed to fetch"), "Plan the motion, then try again."), "Motion can't be approved yet. Plan the motion, then try again.");
  assert.equal(refusal("Motion can't be approved yet.", new Error("No shots."), "ignored"), "Motion can't be approved yet. No shots.");
});
