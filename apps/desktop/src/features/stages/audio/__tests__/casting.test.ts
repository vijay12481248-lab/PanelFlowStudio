import test from "node:test";
import assert from "node:assert/strict";
import { castKeys, castingValue, defaultCasting, setCharacterVoice, setNarratorVoice, voicesFromProviders } from "../casting";

const voice = (id: string, gender?: string) => ({ id, name: id.toUpperCase(), gender });

test("voices come from the primary provider only, with the engine's id and name", () => {
  const voices = voicesFromProviders({
    primary_provider: "p1",
    providers: [
      { id: "p0", voices: [{ id: "other", name: "Other" }] },
      { id: "p1", voices: [{ id: "a", name: "Alpha", gender: "Female", ref: "a.wav" }, { id: "b", name: "Beta" }, { id: "a", name: "Alpha again" }, { name: "Gamma" }] },
    ],
  });
  assert.deepEqual(voices, [
    { id: "a", name: "Alpha", gender: "Female" },
    { id: "b", name: "Beta", gender: undefined },
    { id: "Gamma", name: "Gamma", gender: undefined },
  ]);
});

test("no primary provider, no voices, or a missing response give an empty list", () => {
  assert.deepEqual(voicesFromProviders({ primary_provider: "x", providers: [{ id: "p", voices: [{ id: "a", name: "A" }] }] }), []);
  assert.deepEqual(voicesFromProviders({ primary_provider: "p", providers: [{ id: "p" }] }), []);
  assert.deepEqual(voicesFromProviders(null), []);
  assert.deepEqual(voicesFromProviders({ primary_provider: "p", providers: [{ id: "p", voices: [null, 3, {}] as any }] }), []);
});

test("a character is cast under both its id and its name", () => {
  assert.deepEqual(castKeys({ character_id: "char_1", canonical_name: "Zed" }), ["char_1", "Zed"]);
  assert.deepEqual(castKeys({ canonical_name: "Zed" }), ["Zed"]);
  assert.deepEqual(castKeys({ character_id: "Zed", canonical_name: "Zed" }), ["Zed"]);
});

test("default casting hands out the engine's voices in turn and wraps when there are more characters than voices", () => {
  const characters = [{ character_id: "c1", canonical_name: "One" }, { character_id: "c2", canonical_name: "Two" }, { character_id: "c3", canonical_name: "Three" }];
  const out = defaultCasting(characters, [voice("v1"), voice("v2")], {});
  assert.deepEqual([out.c1, out.c2, out.c3], ["v1", "v2", "v1"]);
  assert.equal(out.One, "v1", "also cast under the name");
});

test("default casting never depends on character names", () => {
  const voices = [voice("v1"), voice("v2"), voice("v3")];
  const a = defaultCasting([{ character_id: "c1", canonical_name: "Marcus" }, { character_id: "c2", canonical_name: "Seraphina" }], voices);
  const b = defaultCasting([{ character_id: "c1", canonical_name: "???" }, { character_id: "c2", canonical_name: "Zed" }], voices);
  assert.deepEqual([a.c1, a.c2], [b.c1, b.c2]);
});

test("default casting keeps every choice already made and does not use up a voice on it", () => {
  const characters = [{ character_id: "c1", canonical_name: "One" }, { character_id: "c2", canonical_name: "Two" }];
  const out = defaultCasting(characters, [voice("v1"), voice("v2")], { c1: "mine", narrator: "n" });
  assert.equal(out.c1, "mine");
  assert.equal(out.narrator, "n");
  assert.equal(out.c2, "v1", "the first free voice goes to the first character that needs one");
});

test("a character already cast under its name counts as cast", () => {
  const out = defaultCasting([{ character_id: "c1", canonical_name: "One" }], [voice("v1")], { One: "mine" });
  assert.equal(out.c1, undefined);
  assert.equal(out.One, "mine");
});

test("default casting matches gender when both are known, rotating within that gender", () => {
  const voices = [voice("f1", "Female"), voice("m1", "Male"), voice("f2", "Female")];
  const characters = [
    { character_id: "c1", canonical_name: "A", gender: "male" },
    { character_id: "c2", canonical_name: "B", gender: "Female" },
    { character_id: "c3", canonical_name: "C", gender: "female" },
    { character_id: "c4", canonical_name: "D", gender: "female" },
    { character_id: "c5", canonical_name: "E", gender: "nonbinary" },
  ];
  const out = defaultCasting(characters, voices);
  assert.deepEqual([out.c1, out.c2, out.c3, out.c4], ["m1", "f1", "f2", "f1"]);
  assert.equal(out.c5, "f1", "an unmatched gender takes the next voice in the general rotation");
});

test("with no voices nothing is assigned, so the engine's own default applies", () => {
  assert.deepEqual(defaultCasting([{ character_id: "c1", canonical_name: "One" }], [], { x: "y" }), { x: "y" });
});

test("choosing a voice for a character sets both keys, and Automatic removes them", () => {
  const character = { character_id: "c1", canonical_name: "One" };
  assert.deepEqual(setCharacterVoice({ other: "o" }, character, "v2"), { other: "o", c1: "v2", One: "v2" });
  assert.deepEqual(setCharacterVoice({ c1: "v2", One: "v2", other: "o" }, character, ""), { other: "o" });
});

test("the narrator voice is set under the three narrator keys, and Automatic removes them", () => {
  assert.deepEqual(setNarratorVoice({}, "v1"), { narrator: "v1", NARRATOR: "v1", The_Narrator: "v1" });
  assert.deepEqual(setNarratorVoice({ narrator: "v1", NARRATOR: "v1", The_Narrator: "v1", c1: "x" }, ""), { c1: "x" });
});

test("the value shown for a character is its id entry, then its name entry, then automatic", () => {
  const character = { character_id: "c1", canonical_name: "One" };
  assert.equal(castingValue({ c1: "a", One: "b" }, character), "a");
  assert.equal(castingValue({ One: "b" }, character), "b");
  assert.equal(castingValue({}, character), "");
});
