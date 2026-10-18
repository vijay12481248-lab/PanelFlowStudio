import React, { useState } from "react";
import { api } from "@panelflow/api-client";
import type { Project, RightsStatus, SourceType, SourceInspection } from "@panelflow/shared-types";
import { Button, Card, Input, Select, Badge, Icons } from "@panelflow/ui";

interface NewProjectScreenProps {
  onBack: () => void;
  onProjectCreated: (project: Project) => void;
}

export const NewProjectScreen: React.FC<NewProjectScreenProps> = ({
  onBack,
  onProjectCreated,
}) => {
  const [storyStyle, setStoryStyle] = useState("Cinematic");
  const [narrationLength, setNarrationLength] = useState("Medium");
  const [language, setLanguage] = useState("en");
  const [autoMusic, setAutoMusic] = useState(false);
  const [autoSfx, setAutoSfx] = useState(false);
  const [musicPath, setMusicPath] = useState("");
  const [sfxPath, setSfxPath] = useState("");
  const [ttsProvider, setTtsProvider] = useState("chatterbox_turbo");
  const [title, setTitle] = useState<string>("");
  const [sourceType, setSourceType] = useState<SourceType>("LOCAL_FOLDER");
  const [sourcePath, setSourcePath] = useState<string>("");
  const [destinationPath, setDestinationPath] = useState<string>("");
  const [rightsStatus, setRightsStatus] = useState<RightsStatus | "">("");
  const [licenseNotes, setLicenseNotes] = useState<string>("");

  const [inspecting, setInspecting] = useState<boolean>(false);
  const [inspection, setInspection] = useState<SourceInspection | null>(null);
  const [inspectError, setInspectError] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleInspect = async () => {
    if (!sourcePath.trim()) return;
    setInspecting(true);
    setInspectError(null);
    setInspection(null);
    try {
      const res = await api.inspectSource(sourcePath.trim());
      setInspection(res);
      if (res.is_valid) setSourceType(res.source_type);
      if (res.title_suggestion && !title.trim()) {
        setTitle(res.title_suggestion);
      }
      if (!res.is_valid && res.error) {
        setInspectError(res.error);
      }
    } catch (err: any) {
      setInspectError(err.message || "Failed to inspect source.");
    } finally {
      setInspecting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);

    if (!title.trim()) {
      setSubmitError("Please enter a project title.");
      return;
    }
    if (!sourcePath.trim()) {
      setSubmitError("Please provide a valid source folder, archive path, or URL.");
      return;
    }
    if (!rightsStatus || rightsStatus === "UNKNOWN") {
      setSubmitError(
        "A valid, verified Rights Status is required. Projects with UNKNOWN rights cannot proceed into the acquisition pipeline."
      );
      return;
    }

    setSubmitting(true);
    try {
      const proj = await api.createProject({
        title: title.trim(),
        source_type: inspection?.is_valid ? inspection.source_type : sourceType,
        source_url: sourcePath.trim(),
        rights_status: rightsStatus as RightsStatus,
        license_info: licenseNotes.trim(),
        settings: {
          ...(destinationPath.trim() ? { project_path: destinationPath.trim() } : {}),
          ...(sourceType === "AUTHORIZED_WEB" ? {
            visual_storytelling: true, story_style: storyStyle,
            narration_length: narrationLength, language, tts_provider: ttsProvider,
            auto_music: autoMusic, auto_sfx: autoSfx, chapter_music_path: musicPath, sfx_library_path: sfxPath,
          } : {}),
        },
      });
      onProjectCreated(proj);
    } catch (err: any) {
      setSubmitError(err.message || "Failed to create project.");
    } finally {
      setSubmitting(false);
    }
  };

  const getSourcePlaceholder = () => {
    switch (sourceType) {
      case "LOCAL_FOLDER":
        return "e.g. C:\\Comics\\Volume_01 or D:\\Comics\\Issue_1";
      case "ZIP_ARCHIVE":
        return "e.g. C:\\Comics\\chapter_01.cbz or D:\\Comics\\volume_01.zip";
      case "AUTHORIZED_WEB":
        return "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-923/";
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6 pb-12">
      {/* Header */}
      <div className="flex items-center gap-3 pb-4 border-b border-zinc-800">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <Icons.ArrowLeft className="w-4 h-4" />
          Back
        </Button>
        <div>
          <h2 className="text-xl font-bold text-zinc-100">Create New Project</h2>
          <p className="text-xs text-zinc-400">
            Define project metadata and declare verified usage rights.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Source Ingestion Card */}
        <Card className="space-y-5">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
            <Icons.Folder className="w-4 h-4 text-indigo-400" />
            1. Source Ingestion
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { type: "LOCAL_FOLDER", label: "Local Folder", icon: Icons.Folder, desc: "Folder of image files" },
              { type: "ZIP_ARCHIVE", label: "ZIP / CBZ Archive", icon: Icons.Archive, desc: ".zip or .cbz comic book" },
              { type: "AUTHORIZED_WEB", label: "Manga Chapter URL", icon: Icons.Globe, desc: "Visual chapter storytelling" },
            ].map((s) => {
              const IconComp = s.icon;
              const isSelected = sourceType === s.type;
              return (
                <button
                  type="button"
                  key={s.type}
                  onClick={() => {
                    setSourceType(s.type as SourceType);
                    setInspection(null);
                  }}
                  className={`p-3.5 rounded-xl border text-left transition-all ${
                    isSelected
                      ? "border-indigo-500 bg-indigo-950/30 ring-1 ring-indigo-500/50"
                      : "border-zinc-800 bg-zinc-950 hover:border-zinc-700"
                  }`}
                >
                  <IconComp className={`w-5 h-5 mb-2 ${isSelected ? "text-indigo-400" : "text-zinc-400"}`} />
                  <div className="font-semibold text-sm text-zinc-200">{s.label}</div>
                  <div className="text-xs text-zinc-500 mt-0.5">{s.desc}</div>
                </button>
              );
            })}
          </div>

          <div className="space-y-2">
            <div className="flex gap-2">
              <Input
                label="Source Path or URL"
                placeholder={getSourcePlaceholder()}
                value={sourcePath}
                onChange={(e) => setSourcePath(e.target.value)}
                required
              />
              <div className="flex items-end">
                <Button
                  type="button"
                  variant="secondary"
                  size="md"
                  onClick={handleInspect}
                  loading={inspecting}
                  disabled={!sourcePath.trim()}
                  className="whitespace-nowrap"
                >
                  Inspect Source
                </Button>
              </div>
            </div>
          </div>

          {/* Inspection Result Preview */}
          {inspectError && (
            <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-lg text-xs text-rose-300 flex items-center gap-2">
              <Icons.AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{inspectError}</span>
            </div>
          )}

          {inspection && inspection.is_valid && (
            <div className="p-3.5 bg-zinc-950 border border-zinc-800 rounded-lg space-y-2 text-xs">
              <div className="flex items-center justify-between text-emerald-400 font-medium">
                <span className="flex items-center gap-1.5">
                  <Icons.CheckCircle className="w-4 h-4" />
                  Source verified successfully
                </span>
                <Badge variant="success">{inspection.total_pages_detected} pages discovered</Badge>
              </div>
              {inspection.title_suggestion && (
                <div className="text-zinc-300">
                  <span className="text-zinc-500">Suggested Title:</span> {inspection.title_suggestion}
                </div>
              )}
            </div>
          )}
        </Card>

        {sourceType === "AUTHORIZED_WEB" && (
          <Card className="space-y-4">
            <h3 className="text-sm font-semibold text-zinc-200">Chapter storytelling</h3>
            <p className="text-xs text-zinc-400">Analyze source panels with a vision model, review the chapter story, then approve original narration before voice generation.</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Select label="Story style" value={storyStyle} onChange={e => setStoryStyle(e.target.value)}>
                {["Cinematic", "Dramatic", "Neutral recap", "Emotional", "Fast YouTube recap", "Detailed storyteller"].map(style => <option key={style}>{style}</option>)}
              </Select>
              <Select label="Narration length" value={narrationLength} onChange={e => setNarrationLength(e.target.value)}>
                {["Short", "Medium", "Detailed"].map(length => <option key={length}>{length}</option>)}
              </Select>
              <Input label="Narration language" value={language} onChange={e => setLanguage(e.target.value)} placeholder="en, hi, ja…" />
              <Input label="Chapter music file (optional)" value={musicPath} onChange={e => setMusicPath(e.target.value)} placeholder="Path to a local music track" />
              <Input label="SFX library folder (optional)" value={sfxPath} onChange={e => setSfxPath(e.target.value)} placeholder="Folder containing sword_draw.wav, wind.wav…" />
              <label className="text-xs text-zinc-300 flex items-center gap-2"><input type="checkbox" checked={autoMusic} onChange={e => setAutoMusic(e.target.checked)} />Generate chapter music with local Lumina / ACE-Step</label>
              <label className="text-xs text-zinc-300 flex items-center gap-2"><input type="checkbox" checked={autoSfx} onChange={e => setAutoSfx(e.target.checked)} />Select sparse effects from the local SFX library</label>
              <Select label="Installed speech adapter" value={ttsProvider} onChange={e => setTtsProvider(e.target.value)}>
                <option value="chatterbox_turbo">Chatterbox Turbo</option>
                <option value="f5_tts">F5-TTS</option>
              </Select>
            </div>
          </Card>
        )}

        {/* Project Information */}
        <Card className="space-y-4">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
            2. Project Information & Storage
          </h3>

          <Input
            label="Project Title"
            placeholder="e.g. The Adventures of Captain Freedom #1"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
          />

          <Input
            label="Project Destination Directory (Optional)"
            placeholder="e.g. C:\My PanelFlow Projects\Captain Freedom (defaults to Windows user workspace)"
            value={destinationPath}
            onChange={(e) => setDestinationPath(e.target.value)}
          />
        </Card>

        {/* Rights & Licensing Card */}
        <Card className="space-y-4 border-amber-900/40 bg-zinc-900/80">
          <div className="flex items-center gap-2 text-amber-400 text-sm font-semibold uppercase tracking-wider">
            <Icons.ShieldCheck className="w-5 h-5" />
            3. Legal & Rights Verification (Mandatory)
          </div>

          <p className="text-xs text-zinc-400 leading-relaxed">
            PanelFlow Studio is designed exclusively for public domain, licensed, user-owned, or explicitly permitted material.
            Material marked <span className="text-rose-400 font-semibold">UNKNOWN</span> cannot be processed.
          </p>

          <Select
            label="Rights Status"
            value={rightsStatus}
            onChange={(e) => setRightsStatus(e.target.value as RightsStatus)}
            required
          >
            <option value="" disabled>-- Select Verified Rights Classification --</option>
            <option value="PUBLIC_DOMAIN">PUBLIC DOMAIN (Verified in public domain / expired copyright)</option>
            <option value="CREATIVE_COMMONS">CREATIVE COMMONS (CC-BY, CC0, CC-BY-SA, etc.)</option>
            <option value="USER_OWNED">USER OWNED (Original work created by user)</option>
            <option value="LICENSED">LICENSED (Commercial or private license held)</option>
            <option value="EXPLICIT_PERMISSION">EXPLICIT PERMISSION (Written authorization from creator)</option>
          </Select>

          <Input
            label="License / Permission Notes (Optional)"
            placeholder="e.g. Public Domain Mark 1.0 (US pre-1928), or Author written email permission dated 2026-03-01"
            value={licenseNotes}
            onChange={(e) => setLicenseNotes(e.target.value)}
            helperText="Documenting license terms or author attribution helps ensure automated downstream publishing compliance."
          />
        </Card>

        {/* Submit Error */}
        {submitError && (
          <div className="p-3.5 bg-rose-950/60 border border-rose-800 rounded-lg text-sm text-rose-200 flex items-center gap-2.5">
            <Icons.XCircle className="w-5 h-5 flex-shrink-0" />
            <span>{submitError}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <Button type="button" variant="ghost" onClick={onBack}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            size="lg"
            loading={submitting}
            disabled={!rightsStatus || rightsStatus === "UNKNOWN"}
          >
            Create & Proceed to Acquisition
          </Button>
        </div>
      </form>
    </div>
  );
};
