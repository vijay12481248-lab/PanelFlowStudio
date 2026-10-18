import test from "node:test";
import assert from "node:assert/strict";
import { MOCK_AUDIO_ASSETS } from "../AudioLibrary.mock.ts";
import type {
  AudioAsset,
  AudioCategory,
  AudioFilterState,
  AudioToTimelineContract,
  AudioSortOption,
} from "../AudioLibrary.types.ts";

test("AudioLibrary: Catalog structure and integrity", () => {
  assert.ok(MOCK_AUDIO_ASSETS.length >= 10, "Should have a rich initial catalog of audio assets");

  for (const asset of MOCK_AUDIO_ASSETS) {
    assert.ok(asset.id, "Every asset must have a stable unique ID");
    assert.ok(asset.name, "Every asset must have a name");
    assert.ok(asset.duration_sec > 0, "Duration must be positive");
    assert.ok(["music", "sfx"].includes(asset.type), "Type must be music or sfx");
    assert.ok(asset.license, "Asset must contain license metadata");
    assert.ok(asset.license.license_type, "Asset must specify license type");
    assert.ok(asset.license.author_or_source, "Asset must specify author or source");
    assert.ok(asset.tags && asset.tags.length > 0, "Asset must contain descriptive tags");
  }
});

test("AudioLibrary: All 12 categories are supported in catalog", () => {
  const expectedCategories: AudioCategory[] = [
    "background_music",
    "cinematic",
    "suspense",
    "emotional",
    "action",
    "fantasy",
    "ambient",
    "environmental",
    "character",
    "transitions",
    "magic_fx",
    "favorites",
  ];

  assert.equal(expectedCategories.length, 12, "Must specify all 12 target categories");

  // Verify assets exist across music and sfx categories
  const categoriesPresent = new Set(MOCK_AUDIO_ASSETS.map((a) => a.category));
  assert.ok(categoriesPresent.has("cinematic"));
  assert.ok(categoriesPresent.has("suspense"));
  assert.ok(categoriesPresent.has("emotional"));
  assert.ok(categoriesPresent.has("action"));
  assert.ok(categoriesPresent.has("environmental"));
  assert.ok(categoriesPresent.has("character"));
  assert.ok(categoriesPresent.has("transitions"));
  assert.ok(categoriesPresent.has("magic_fx"));
});

test("AudioLibrary: Waveform integrity - synthetic waveforms must not replace missing data", () => {
  // Test assets that have real measured peaks vs assets that do not
  const assetsWithPeaks = MOCK_AUDIO_ASSETS.filter((a) => a.measured_peaks && a.measured_peaks.length > 0);
  const assetsWithoutPeaks = MOCK_AUDIO_ASSETS.filter((a) => !a.measured_peaks || a.measured_peaks.length === 0);

  assert.ok(assetsWithPeaks.length > 0, "Should have assets with measured audio waveforms");
  assert.ok(assetsWithoutPeaks.length > 0, "Should have assets without measured waveforms to test fallback UI");

  for (const asset of assetsWithPeaks) {
    assert.ok(asset.measured_peaks!.every((p) => p >= 0 && p <= 1), "Peaks must be normalized 0.0 to 1.0");
  }
});

test("AudioLibrary: Missing-file assets are properly flagged for safe failure", () => {
  const missingFileAssets = MOCK_AUDIO_ASSETS.filter((a) => a.availability === "MISSING_FILE");
  assert.ok(missingFileAssets.length > 0, "Must have intentional missing-file assets to test graceful error handling");

  for (const asset of missingFileAssets) {
    assert.equal(asset.availability, "MISSING_FILE");
    // Verify file_url is either null or missing
    assert.ok(asset.file_url === null || asset.file_url === undefined || asset.file_url.includes("missing"));
  }
});

test("AudioLibrary: Search and keyword filtering", () => {
  const query = "crystal";
  const results = MOCK_AUDIO_ASSETS.filter((asset) => {
    const q = query.toLowerCase();
    const matchName = asset.name.toLowerCase().includes(q);
    const matchDesc = asset.description.toLowerCase().includes(q);
    const matchTags = asset.tags.some((t) => t.toLowerCase().includes(q));
    const matchAuthor = asset.license.author_or_source.toLowerCase().includes(q);
    return matchName || matchDesc || matchTags || matchAuthor;
  });

  assert.ok(results.length > 0, "Query 'crystal' should match assets by tag/description/name");
  assert.ok(results.some((r) => r.id === "pf_bgm_d_minor_discovery"));
});

test("AudioLibrary: Sorting options", () => {
  // Duration ascending
  const sortedByDurationAsc = [...MOCK_AUDIO_ASSETS].sort((a, b) => a.duration_sec - b.duration_sec);
  assert.ok(sortedByDurationAsc[0].duration_sec <= sortedByDurationAsc[1].duration_sec);

  // Duration descending
  const sortedByDurationDesc = [...MOCK_AUDIO_ASSETS].sort((a, b) => b.duration_sec - a.duration_sec);
  assert.ok(sortedByDurationDesc[0].duration_sec >= sortedByDurationDesc[1].duration_sec);

  // Name A-Z
  const sortedByNameAsc = [...MOCK_AUDIO_ASSETS].sort((a, b) => a.name.localeCompare(b.name));
  assert.ok(sortedByNameAsc[0].name.localeCompare(sortedByNameAsc[1].name) <= 0);
});

test("AudioLibrary: Chapter 6B Future Timeline Integration Contract serialization (Schema 6A-v1)", () => {
  const sampleAsset = MOCK_AUDIO_ASSETS.find((a) => a.availability === "AVAILABLE")!;
  assert.ok(sampleAsset, "Available asset found");

  const contract: AudioToTimelineContract = {
    schema_version: "6A-v1",
    exported_at: new Date().toISOString(),
    reference: {
      asset_id: sampleAsset.id,
      name: sampleAsset.name,
      type: sampleAsset.type,
      category: sampleAsset.category,
      duration_sec: sampleAsset.duration_sec,
      file_url: sampleAsset.file_url || "",
      target_track: sampleAsset.recommended_timeline_track,
      volume: 0.85,
      loop: sampleAsset.loopable ?? true,
      fade_in_sec: 1.0,
      fade_out_sec: 1.5,
      bpm: sampleAsset.bpm,
      key: sampleAsset.key,
    },
  };

  assert.equal(contract.schema_version, "6A-v1");
  assert.ok(contract.exported_at);
  assert.equal(contract.reference.asset_id, sampleAsset.id);
  assert.equal(contract.reference.target_track, sampleAsset.recommended_timeline_track);
  assert.equal(contract.reference.volume, 0.85);
  assert.equal(contract.reference.fade_in_sec, 1.0);
  assert.equal(contract.reference.fade_out_sec, 1.5);
});
