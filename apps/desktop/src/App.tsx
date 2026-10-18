import React, { useState, useEffect } from "react";
import { version as appVersion } from "../package.json";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { Badge, Button, Icons } from "@panelflow/ui";
import { ProjectsScreen } from "./screens/ProjectsScreen";
import { NewProjectScreen } from "./screens/NewProjectScreen";
import { AcquisitionScreen } from "./screens/AcquisitionScreen";
import { PageReviewScreen } from "./screens/PageReviewScreen";
import { PanelReviewScreen } from "./screens/PanelReviewScreen";
import { OCRReviewScreen } from "./screens/OCRReviewScreen";
import { StoryReviewScreen } from "./screens/StoryReviewScreen";
import { ScriptReviewScreen } from "./screens/ScriptReviewScreen";
import { AudioScreen } from "./screens/AudioScreen";
import { MotionScreen } from "./screens/MotionScreen";
import { RenderScreen } from "./screens/RenderScreen";
import { StoryEditorScreen } from "./screens/StoryEditorScreen";
import { PipelineNavbar } from "./components/PipelineNavbar";
import { ProviderHealthModal } from "./components/ProviderHealthModal";

type ScreenMode =
  | "projects"
  | "new_project"
  | "story_editor"
  | "acquisition"
  | "review"
  | "panels"
  | "ocr"
  | "story"
  | "script"
  | "audio"
  | "motion"
  | "render";

export const App: React.FC = () => {
  const [currentScreen, setCurrentScreen] = useState<ScreenMode>("projects");
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [engineConnected, setEngineConnected] = useState<boolean>(false);
  const [engineVersion, setEngineVersion] = useState<string>("");
  const [healthModalOpen, setHealthModalOpen] = useState<boolean>(false);
  const [retrying, setRetrying] = useState<boolean>(false);

  const checkEngine = async () => {
    try {
      const h = await api.checkHealth();
      setEngineConnected(h.status === "healthy");
      setEngineVersion(h.version);
    } catch {
      setEngineConnected(false);
    }
  };

  const handleRetryEngine = async () => {
    setRetrying(true);
    try {
      if (typeof window !== "undefined" && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window)) {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          await invoke("start_engine_cmd");
        } catch (e) {
          console.warn("[PanelFlow] Tauri start_engine_cmd notice:", e);
        }
      }
      for (let i = 0; i < 6; i++) {
        await new Promise((r) => setTimeout(r, 600));
        try {
          const h = await api.checkHealth();
          if (h.status === "healthy") {
            setEngineConnected(true);
            setEngineVersion(h.version);
            setRetrying(false);
            return;
          }
        } catch {
          // continue polling
        }
      }
    } finally {
      await checkEngine();
      setRetrying(false);
    }
  };

  useEffect(() => {
    checkEngine();
    const intervalTime = engineConnected ? 8000 : 1500;
    const timer = setInterval(checkEngine, intervalTime);
    return () => clearInterval(timer);
  }, [engineConnected]);

  // Dedicated Video-First Story Editor View
  if (currentScreen === "story_editor" && selectedProject) {
    return (
      <StoryEditorScreen
        project={selectedProject}
        onBack={() => {
          setCurrentScreen("projects");
          setSelectedProject(null);
        }}
        onExport={() => {
          setCurrentScreen("render");
        }}
      />
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      {/* Top Application Bar */}
      <header className="h-14 border-b border-zinc-800 bg-zinc-900/50 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-40">
        <div className="flex items-center gap-3">
          <div
            className="flex items-center gap-2 cursor-pointer font-bold text-lg text-indigo-400 hover:text-indigo-300 transition-colors"
            onClick={() => {
              setCurrentScreen("projects");
              setSelectedProject(null);
            }}
          >
            <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md shadow-indigo-600/30">
              P
            </div>
            <span>PanelFlow Studio</span>
          </div>

          <span className="text-zinc-600 text-sm hidden sm:inline">|</span>
          <span className="text-xs text-zinc-400 hidden sm:inline font-medium">
            AI-Assisted Motion Comic Ingestion & Production Engine
          </span>
        </div>

        {/* Engine Status & Tools */}
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setHealthModalOpen(true)}
            className="text-xs text-zinc-400 hover:text-zinc-200"
            title="Inspect local models and tool engine status"
          >
            <Icons.ShieldCheck className="w-4 h-4 mr-1.5 text-indigo-400" />
            Tools & Models
          </Button>

          <div className="flex items-center gap-2 text-xs">
            <span
              className={`w-2 h-2 rounded-full ${
                engineConnected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"
              }`}
            />
            <span className="text-zinc-400 font-mono hidden md:inline">
              {engineConnected ? `Local Engine v${engineVersion}` : "Engine Offline"}
            </span>
          </div>

          <Badge variant={engineConnected ? "success" : "danger"} className="hidden sm:inline-flex">
            {engineConnected ? "CONNECTED" : "DISCONNECTED"}
          </Badge>
        </div>
      </header>

      {/* Main Screen Content */}
      <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full">
        {!engineConnected ? (
          <div className="flex flex-col items-center justify-center min-h-[60vh] text-center space-y-5">
            <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 shadow-lg shadow-rose-950/40">
              <Icons.AlertTriangle className="w-8 h-8 text-rose-400" />
            </div>
            <div className="space-y-2">
              <h2 className="text-2xl font-bold text-zinc-100">Processing engine unavailable</h2>
              <p className="text-sm text-zinc-400 max-w-md mx-auto">
                The local Python processing engine on <code className="text-zinc-200 bg-zinc-800 px-1.5 py-0.5 rounded text-xs font-mono">127.0.0.1:8765</code> is not responding. Please ensure the local service is running or retry connection.
              </p>
              <p className="text-xs text-zinc-500 max-w-md mx-auto">
                If running in development mode, start the engine from your terminal using: <code className="text-zinc-300 bg-zinc-800 px-1 py-0.5 rounded font-mono">npm run engine</code>
              </p>
            </div>
            <Button
              variant="primary"
              onClick={handleRetryEngine}
              disabled={retrying}
              className="mt-2"
            >
              <Icons.Rotate className={`w-4 h-4 mr-2 ${retrying ? "animate-spin" : ""}`} />
              {retrying ? "Starting Engine..." : "Retry Engine Connection"}
            </Button>
          </div>
        ) : (
          <>
            {/* Top Interactive Pipeline Progression Navbar */}
            {selectedProject && currentScreen !== "projects" && currentScreen !== "new_project" && (
              <div className="mb-6 bg-zinc-900/60 border border-zinc-800 rounded-xl p-2.5">
                <PipelineNavbar
                  currentStage={selectedProject.current_stage}
                  currentScreen={currentScreen}
                  onNavigate={(stageKey) => setCurrentScreen(stageKey as ScreenMode)}
                  staleStages={selectedProject.stale_stages}
                />
              </div>
            )}

            {currentScreen === "projects" && (
              <ProjectsScreen
                onNewProject={() => setCurrentScreen("new_project")}
                onOpenAcquisition={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("acquisition");
                }}
                onOpenReview={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("review");
                }}
                onOpenPanels={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("panels");
                }}
                onOpenOCR={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("ocr");
                }}
                onOpenStory={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("story");
                }}
                onOpenScript={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("script");
                }}
                onOpenAudio={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("audio");
                }}
                onOpenMotion={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("motion");
                }}
                onOpenRender={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("render");
                }}
                onOpenStoryEditor={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("story_editor");
                }}
              />
            )}

            {currentScreen === "new_project" && (
              <NewProjectScreen
                onBack={() => setCurrentScreen("projects")}
                onProjectCreated={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("acquisition");
                }}
              />
            )}

            {currentScreen === "acquisition" && selectedProject && (
              <AcquisitionScreen
                project={selectedProject}
                onBack={() => {
                  setCurrentScreen("projects");
                  setSelectedProject(null);
                }}
                onReviewPages={() => setCurrentScreen("review")}
              />
            )}

            {currentScreen === "review" && selectedProject && (
              <PageReviewScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("acquisition")}
                onAcquisitionConfirmed={(updated) => {
                  setSelectedProject(updated);
                  setCurrentScreen("panels");
                }}
                onProceedToPanels={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("panels");
                }}
              />
            )}

            {currentScreen === "panels" && selectedProject && (
              <PanelReviewScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("review")}
                onPanelsApproved={(updated) => {
                  setSelectedProject(updated);
                  setCurrentScreen("ocr");
                }}
                onProceedToOCR={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("ocr");
                }}
              />
            )}

            {currentScreen === "ocr" && selectedProject && (
              <OCRReviewScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("panels")}
                onOCRApproved={(updated) => {
                  setSelectedProject(updated);
                  setCurrentScreen("story");
                }}
                onProceedToStory={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("story");
                }}
              />
            )}

            {currentScreen === "story" && selectedProject && (
              <StoryReviewScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("ocr")}
                onStoryApproved={(updated) => {
                  setSelectedProject(updated);
                  setCurrentScreen("script");
                }}
                onProceedToScript={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("script");
                }}
              />
            )}

            {currentScreen === "script" && selectedProject && (
              <ScriptReviewScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("story")}
                onScriptApproved={(updated) => {
                  setSelectedProject(updated);
                  setCurrentScreen("audio");
                }}
                onProceedToAudio={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("audio");
                }}
                onProjectUpdated={(updated) => {
                  setSelectedProject(updated);
                }}
              />
            )}

            {currentScreen === "audio" && selectedProject && (
              <AudioScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("script")}
                onAudioApproved={(updated) => {
                  setSelectedProject(updated);
                  setCurrentScreen("motion");
                }}
                onProceedToMotion={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("motion");
                }}
              />
            )}

            {currentScreen === "motion" && selectedProject && (
              <MotionScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("audio")}
                onMotionApproved={(updated) => {
                  setSelectedProject(updated);
                  setCurrentScreen("render");
                }}
                onProceedToRender={(proj) => {
                  setSelectedProject(proj);
                  setCurrentScreen("render");
                }}
              />
            )}

            {currentScreen === "render" && selectedProject && (
              <RenderScreen
                project={selectedProject}
                onBack={() => setCurrentScreen("motion")}
                onRenderComplete={(updated) => {
                  setSelectedProject(updated);
                }}
              />
            )}
          </>
        )}
      </main>

      {/* Provider Health Modal */}
      <ProviderHealthModal
        open={healthModalOpen}
        onClose={() => setHealthModalOpen(false)}
      />

      {/* Footer */}
      <footer className="border-t border-zinc-900 py-3 px-6 text-center text-xs text-zinc-500">
        PanelFlow Studio v{appVersion} • Local-First Architecture • Fully Integrated Pipeline
      </footer>
    </div>
  );
};
export default App;
