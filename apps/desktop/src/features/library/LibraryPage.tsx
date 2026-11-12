import React, { useState, useMemo, useRef, useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Project, Page } from "@panelflow/shared-types";
import {
  Button,
  Chip,
  Dialog,
  EmptyState,
  GlassPanel,
  IconButton,
  Input,
  PageHeader,
  Skeleton,
  Tabs,
  useToast,
} from "@panelflow/ui-v2";
import {
  Music,
  ImageIcon,
  Mic,
  Play,
  Pause,
  ExternalLink,
  Search,
  Volume2,
  FolderOpen,
  ChevronLeft,
  ChevronRight,
  Layers,
  Sparkles,
} from "lucide-react";
import { paths, isChronoFlowProject, stageForProject } from "../../app/routes";
import { AudioLibrary } from "../../components/audio-library";
import type { AudioToTimelineContract } from "../../components/audio-library/AudioLibrary.types";

type LibraryTab = "audio" | "media" | "voices";

export const LibraryPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { show } = useToast();

  // Resolve active tab from URL (/library/audio, /library/media, /library/voices)
  const initialTab: LibraryTab = useMemo(() => {
    const segment = location.pathname.split("/")[2];
    if (segment === "media" || segment === "images") return "media";
    if (segment === "voices") return "voices";
    return "audio";
  }, [location.pathname]);

  const [activeTab, setActiveTab] = useState<LibraryTab>(initialTab);

  const handleTabChange = (tab: string) => {
    const nextTab = tab as LibraryTab;
    setActiveTab(nextTab);
    if (location.pathname.startsWith("/library")) {
      navigate(paths.library(nextTab), { replace: true });
    }
  };

  // Toast handler when user clicks send to timeline or project from AudioLibrary
  const handleSendToTimeline = (contract: AudioToTimelineContract) => {
    show(`"${contract.reference.name}" (${contract.reference.target_track}) selected for timeline integration.`, "ok");
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col gap-5 p-6 md:p-8">
      <PageHeader
        title="Library"
        meta={<span>Browse soundtrack BGM, sound effects, project slices, and narrator voice profiles.</span>}
      />

      <Tabs
        value={activeTab}
        onValueChange={handleTabChange}
        tabs={[
          { value: "audio", label: "🎵 Audio & Music" },
          { value: "media", label: "🖼️ Visual Media & Slices" },
          { value: "voices", label: "🎙️ Voice Cast" },
        ]}
      >
        {activeTab === "audio" && (
          <div className="h-[calc(100vh-230px)] min-h-[620px] w-full overflow-hidden rounded-2xl border border-edge shadow-2xl">
            <AudioLibrary onSendToTimeline={handleSendToTimeline} />
          </div>
        )}

        {activeTab === "media" && <ProjectMediaBrowser />}

        {activeTab === "voices" && <VoiceCastBrowser />}
      </Tabs>
    </div>
  );
};

/** Project Visual Media and Slices Browser */
const ProjectMediaBrowser: React.FC = () => {
  const navigate = useNavigate();
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects(),
  });

  const projects = projectsQuery.data ?? [];
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [previewPage, setPreviewPage] = useState<Page | null>(null);

  // Initialize selected project
  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  const selectedProject = useMemo(
    () => projects.find((p) => p.id === selectedProjectId) ?? projects[0],
    [projects, selectedProjectId]
  );

  // Pages / slices query for selected project
  const pagesQuery = useQuery({
    queryKey: ["project-pages", selectedProjectId],
    queryFn: () => api.listPages(selectedProjectId),
    enabled: Boolean(selectedProjectId),
  });

  const pages = pagesQuery.data ?? [];
  const filteredPages = useMemo(() => {
    if (!searchQuery.trim()) return pages;
    const q = searchQuery.toLowerCase();
    return pages.filter(
      (p) =>
        String(p.sequence).includes(q) ||
        (p.filename && p.filename.toLowerCase().includes(q))
    );
  }, [pages, searchQuery]);

  const openProject = (project: Project) => {
    navigate(
      isChronoFlowProject(project)
        ? paths.chronoflow({ projectId: project.id })
        : paths.stage(project.id, stageForProject(project))
    );
  };

  if (projectsQuery.isLoading) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-12 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <GlassPanel className="p-8">
        <EmptyState
          title="No project visual media found"
          description="Create a project to import manga chapters, comic pages, or AI video storyboard slices."
          action={<Button variant="primary" onClick={() => navigate(paths.create("new"))}>Create a project</Button>}
        />
      </GlassPanel>
    );
  }

  return (
    <div className="grid gap-6">
      {/* Top Project Selector and Info Bar */}
      <GlassPanel className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <label htmlFor="project-picker" className="text-xs font-semibold uppercase tracking-wider text-fg-dim">
            Select Project:
          </label>
          <select
            id="project-picker"
            value={selectedProjectId}
            onChange={(e) => setSelectedProjectId(e.target.value)}
            className="rounded-ctl border border-edge bg-glass-hi px-3 py-1.5 text-sm font-medium text-fg shadow-sm outline-none focus:border-accent"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title} ({p.current_stage})
              </option>
            ))}
          </select>
        </div>

        {selectedProject && (
          <div className="flex items-center gap-3">
            <Chip tone="accent">{selectedProject.current_stage}</Chip>
            <span className="text-xs text-fg-dim">
              {pages.length} {pages.length === 1 ? "slice / page" : "slices / pages"}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => openProject(selectedProject)}
            >
              <FolderOpen className="mr-1.5 size-3.5" />
              Open in Editor
            </Button>
          </div>
        )}
      </GlassPanel>

      {/* Selected Project Details & Search */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <Layers className="size-4 text-accent" />
          <h2 className="text-sm font-semibold text-fg">
            {selectedProject?.title} Media Assets
          </h2>
        </div>

        <div className="w-full md:w-72">
          <Input
            type="search"
            placeholder="Search slice number or filename..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Slices Grid */}
      {pagesQuery.isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[3/4] w-full rounded-card" />
          ))}
        </div>
      ) : filteredPages.length === 0 ? (
        <GlassPanel className="p-8 text-center text-sm text-fg-dim">
          No slices match your search filter.
        </GlassPanel>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {filteredPages.map((page, idx) => {
            const imageUrl = api.getPageImageUrl(selectedProjectId, page.id);
            return (
              <button
                type="button"
                key={page.id}
                onClick={() => setPreviewPage(page)}
                className="group relative flex flex-col overflow-hidden rounded-card border border-edge bg-glass transition-all duration-200 hover:-translate-y-1 hover:border-glow/50 hover:shadow-xl text-left cursor-pointer"
              >
                <div className="relative aspect-[3/4] w-full overflow-hidden bg-ink">
                  <img
                    src={imageUrl}
                    alt={`Slice #${page.sequence}`}
                    loading="lazy"
                    className="size-full object-cover transition-transform duration-300 group-hover:scale-105"
                  />
                  <span className="absolute bottom-1.5 left-1.5 rounded bg-black/75 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white">
                    #{page.sequence}
                  </span>
                </div>
                <div className="p-2">
                  <span className="block truncate text-xs font-medium text-fg">
                    {page.filename || `Slice ${page.sequence}`}
                  </span>
                  <span className="block text-[11px] text-fg-dim">
                    {page.width && page.height ? `${page.width} × ${page.height} px` : "Ready"}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Lightbox / Slice Preview Modal */}
      {previewPage && (
        <Dialog
          open={Boolean(previewPage)}
          onOpenChange={(open) => {
            if (!open) setPreviewPage(null);
          }}
          title={`${selectedProject?.title} — Slice #${previewPage.sequence}`}
          description={previewPage.filename || `Page ID: ${previewPage.id}`}
          footer={
            <div className="flex w-full items-center justify-between">
              <span className="text-xs text-fg-dim">
                {previewPage.width && previewPage.height ? `${previewPage.width} × ${previewPage.height} px` : "WebP / PNG"}
              </span>
              <Button variant="secondary" onClick={() => setPreviewPage(null)}>
                Close Preview
              </Button>
            </div>
          }
        >
          <div className="flex max-h-[70vh] items-center justify-center overflow-auto rounded-lg bg-ink p-2">
            <img
              src={api.getPageImageUrl(selectedProjectId, previewPage.id)}
              alt={`Slice #${previewPage.sequence}`}
              className="max-h-[65vh] w-auto rounded object-contain shadow-2xl"
            />
          </div>
        </Dialog>
      )}
    </div>
  );
};

/** Voice Cast & Speech Provider Browser */
const VoiceCastBrowser: React.FC = () => {
  const providersQuery = useQuery({
    queryKey: ["audio-providers"],
    queryFn: () => api.getAudioProviders(),
  });

  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const audio = new Audio();
    audioRef.current = audio;
    audio.onended = () => setPlayingVoiceId(null);
    audio.onerror = () => setPlayingVoiceId(null);
    return () => {
      audio.pause();
      audio.src = "";
    };
  }, []);

  const handlePlayVoice = (voiceId: string, sampleUrl?: string) => {
    if (!audioRef.current) return;
    const audio = audioRef.current;

    if (playingVoiceId === voiceId) {
      audio.pause();
      setPlayingVoiceId(null);
      return;
    }

    // Play demo sample audio or fallback to sample tone
    audio.src = sampleUrl || "/assets/demo/aria_narration_sample.mp3";
    audio.currentTime = 0;
    audio.play()
      .then(() => setPlayingVoiceId(voiceId))
      .catch(() => setPlayingVoiceId(null));
  };

  const providers = providersQuery.data?.providers ?? [];
  const primaryProvider = providersQuery.data?.primary_provider ?? "chatterbox_turbo";

  const allVoices = useMemo(() => {
    const list: Array<{ id: string; name: string; gender?: string; provider: string; ref?: string }> = [];
    for (const p of providers) {
      for (const v of p.voices ?? []) {
        list.push({
          id: v.id,
          name: v.name || v.id,
          gender: v.gender,
          provider: p.name || p.id,
          ref: v.ref,
        });
      }
    }
    return list;
  }, [providers]);

  if (providersQuery.isLoading) {
    return (
      <div className="grid gap-4">
        <Skeleton className="h-16 w-full" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Skeleton className="h-44 w-full" />
          <Skeleton className="h-44 w-full" />
          <Skeleton className="h-44 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-6">
      {/* Primary Voice Engine Status Banner */}
      <GlassPanel className="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Mic className="size-4 text-accent" />
            <h2 className="text-sm font-semibold text-fg">Active Speech Engine</h2>
            <Chip tone="ok">Ready</Chip>
          </div>
          <p className="mt-1 text-xs text-fg-dim">
            Default Provider: <span className="font-semibold text-fg font-mono">{primaryProvider}</span> • 48 kHz High-Fidelity Studio Voices
          </p>
        </div>

        <div className="text-xs text-fg-dim">
          <span>{allVoices.length} Available Narrator & Character Voices</span>
        </div>
      </GlassPanel>

      {/* Voice Profiles Grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {allVoices.map((voice) => {
          const isPlaying = playingVoiceId === voice.id;
          return (
            <GlassPanel
              key={voice.id}
              className="flex flex-col justify-between p-5 transition-all duration-200 hover:border-glow/40"
            >
              <div>
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="grid size-10 place-items-center rounded-full bg-accent/20 text-accent font-bold">
                      {voice.gender === "Female" ? "♀" : "♂"}
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-fg">{voice.name}</h3>
                      <span className="text-xs text-fg-dim">{voice.provider}</span>
                    </div>
                  </div>

                  {voice.gender && (
                    <Chip tone="neutral" className="text-[11px]">
                      {voice.gender}
                    </Chip>
                  )}
                </div>

                <p className="mt-4 text-xs leading-relaxed text-fg-dim">
                  {voice.id === "the narrator"
                    ? "Warm, authoritative, and cinematic narrator voice. Balanced tone suited for webtoons and documentary pacing."
                    : voice.id === "marcus"
                    ? "Deep, resonant male voice with commanding baritone resonance. Ideal for action protagonists and warriors."
                    : "Bright, expressive cinematic female voice. Suited for emotional reveals, heroines, and dialogue."}
                </p>
              </div>

              <div className="mt-5 flex items-center justify-between border-t border-edge pt-3">
                <span className="font-mono text-[10px] text-fg-faint">
                  {voice.ref || "engine_native.wav"}
                </span>

                <Button
                  variant={isPlaying ? "primary" : "secondary"}
                  size="sm"
                  onClick={() => handlePlayVoice(voice.id)}
                >
                  {isPlaying ? (
                    <>
                      <Pause className="mr-1.5 size-3.5" />
                      Pause Preview
                    </>
                  ) : (
                    <>
                      <Play className="mr-1.5 size-3.5" />
                      Audition Voice
                    </>
                  )}
                </Button>
              </div>
            </GlassPanel>
          );
        })}
      </div>
    </div>
  );
};
