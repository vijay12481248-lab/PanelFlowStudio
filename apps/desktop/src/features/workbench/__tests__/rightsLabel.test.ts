import test from "node:test";
import assert from "node:assert/strict";
import { rightsLabel } from "../rightsLabel";

test("known rights values get plain words and only unknown rights warn", () => {
  assert.deepEqual(rightsLabel("UNKNOWN"), { word: "Rights unknown", tone: "warn" });
  assert.deepEqual(rightsLabel("PUBLIC_DOMAIN"), { word: "Public domain", tone: "ok" });
  assert.deepEqual(rightsLabel("CREATIVE_COMMONS"), { word: "Creative Commons", tone: "ok" });
  assert.deepEqual(rightsLabel("LICENSED"), { word: "Licensed", tone: "ok" });
  assert.deepEqual(rightsLabel("USER_OWNED"), { word: "Your own work", tone: "ok" });
  assert.deepEqual(rightsLabel("EXPLICIT_PERMISSION"), { word: "Permission granted", tone: "ok" });
  assert.deepEqual(rightsLabel("COMMENTARY_REVIEW"), { word: "Commentary and review", tone: "ok" });
});

test("values the engine uses that are not in the type are humanised, never shown raw", () => {
  assert.deepEqual(rightsLabel("AUTHORIZED_WEB"), { word: "Authorized web", tone: "neutral" });
  assert.deepEqual(rightsLabel("LOCAL_DIRECTORY"), { word: "Local directory", tone: "neutral" });
  assert.deepEqual(rightsLabel(""), { word: "Rights not recorded", tone: "neutral" });
});
