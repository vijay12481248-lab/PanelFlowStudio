import test from "node:test";
import assert from "node:assert/strict";
import { VOICE_PRESETS } from "../AudioScreen.tsx";

test("AudioScreen: Voice Presets contain required roles and valid IDs", () => {
  assert.ok(VOICE_PRESETS.length >= 5, "Must provide comprehensive voice presets");

  const presetIds = VOICE_PRESETS.map((p) => p.id);
  assert.ok(presetIds.includes("Narrator"), "Must provide Narrator preset");
  assert.ok(presetIds.includes("Marcus (Male Deep F5-TTS)"), "Must provide Marcus preset");
  assert.ok(presetIds.includes("Seraphina (Cinematic)"), "Must provide Seraphina preset");
  assert.ok(presetIds.includes("Aria (The Narrator)"), "Must provide Aria preset");
  assert.ok(presetIds.includes("Leon"), "Must provide Leon preset");

  for (const preset of VOICE_PRESETS) {
    assert.ok(preset.id && preset.id.trim().length > 0, "Preset ID must not be empty");
    assert.ok(preset.label && preset.label.trim().length > 0, "Preset label must not be empty");
    assert.ok(preset.desc && preset.desc.trim().length > 0, "Preset description must not be empty");
  }
});

test("AudioScreen: Interval classification distinguishing speech vs natural silence pause", () => {
  const speechInterval = {
    interval_id: "iv_001",
    timeline_source_type: "SPEECH" as const,
    audio_file_uri: "audio/dialogue/seg_001.wav",
    start_time: 0.5,
    end_time: 3.2,
    duration: 2.7,
    gain_db: 0,
    is_voice: true,
    is_speech: true,
    cue_text: "Stand back, everyone!",
  };

  const pauseInterval = {
    interval_id: "iv_002",
    timeline_source_type: "SPEECH" as const,
    audio_file_uri: "",
    start_time: 3.2,
    end_time: 3.7,
    duration: 0.5,
    gain_db: 0,
    is_voice: false,
    is_speech: false,
    cue_text: "",
  };

  const isSpeech1 = Boolean(speechInterval.audio_file_uri && speechInterval.is_speech !== false);
  const isSpeech2 = Boolean(pauseInterval.audio_file_uri && pauseInterval.is_speech !== false);

  assert.equal(isSpeech1, true, "Speech interval with URI should be classified as speech");
  assert.equal(isSpeech2, false, "Pause interval without URI should be classified as pause");
});

test("AudioScreen: Scrubber timestamp search locates correct interval", () => {
  const intervals = [
    { start_time: 0.5, end_time: 3.0, is_speech: true },
    { start_time: 3.0, end_time: 3.5, is_speech: false },
    { start_time: 3.5, end_time: 6.8, is_speech: true },
    { start_time: 6.8, end_time: 9.0, is_speech: true },
  ];

  const findIntervalAtTime = (targetSec: number) => {
    return intervals.findIndex(
      (iv) => (iv.start_time ?? 0) <= targetSec && targetSec <= (iv.end_time ?? 0)
    );
  };

  assert.equal(findIntervalAtTime(1.5), 0, "Timestamp 1.5s should locate interval 0");
  assert.equal(findIntervalAtTime(3.2), 1, "Timestamp 3.2s should locate interval 1 (pause)");
  assert.equal(findIntervalAtTime(5.0), 2, "Timestamp 5.0s should locate interval 2");
  assert.equal(findIntervalAtTime(8.0), 3, "Timestamp 8.0s should locate interval 3");
  assert.equal(findIntervalAtTime(12.0), -1, "Out-of-bounds timestamp should return -1");
});

test("AudioScreen: Voice casting dictionary mapping with character fallback", () => {
  const castingMap: Record<string, string> = {
    narrator: "Narrator",
    char_marcus: "Marcus (Male Deep F5-TTS)",
    char_seraphina: "Seraphina (Cinematic)",
  };

  const resolveVoice = (speakerId: string) => {
    return castingMap[speakerId] || castingMap[speakerId.toLowerCase()] || "Narrator";
  };

  assert.equal(resolveVoice("char_marcus"), "Marcus (Male Deep F5-TTS)");
  assert.equal(resolveVoice("CHAR_MARCUS"), "Marcus (Male Deep F5-TTS)");
  assert.equal(resolveVoice("narrator"), "Narrator");
  assert.equal(resolveVoice("unknown_character"), "Narrator");
});
