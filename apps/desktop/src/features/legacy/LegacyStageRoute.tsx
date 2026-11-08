import React from "react";
import { Navigate, useNavigate, useParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Zap } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { Button, ErrorState, GlassPanel, PageHeader, Skeleton } from "@panelflow/ui-v2";
import { AcquisitionScreen } from "../../screens/AcquisitionScreen";
import { PageReviewScreen } from "../../screens/PageReviewScreen";
import { PanelReviewScreen } from "../../screens/PanelReviewScreen";
import { OCRReviewScreen } from "../../screens/OCRReviewScreen";
import { StoryReviewScreen } from "../../screens/StoryReviewScreen";
import { ScriptReviewScreen } from "../../screens/ScriptReviewScreen";
import { AudioScreen } from "../../screens/AudioScreen";
import { MotionScreen } from "../../screens/MotionScreen";
import { RenderScreen } from "../../screens/RenderScreen";
import { PipelineNavbar } from "../../components/PipelineNavbar";
import { AutoPilotModal } from "../../components/AutoPilotModal";
import { paths, nextStage, prevStage, type Stage } from "../../app/routes";
import { resolveStageRoute } from "./resolveStageRoute";

/** The old PipelineNavbar and AutoPilotModal speak in the old screen keys; translate both ways. */
const NAVBAR_KEY_TO_STAGE: Record<string, Stage | "story_editor"> = {
  acquisition: "acquire", review: "pages", panels: "panels", ocr: "ocr", story: "story",
  script: "script", audio: "audio", motion: "motion", render: "render", story_editor: "story_editor",
};
const stageToNavbarKey = (stage: Stage): string => ({ acquire: "acquisition", pages: "review", publish: "render" } as Record<string, string>)[stage] ?? stage;
const AUTOPILOT_STAGE: Record<string, Stage> = {
  pages: "pages", panels: "panels", ocr: "ocr", story: "story", script: "script", audio: "audio", motion: "motion", render: "render", packaging: "publish",
};

const StageScreen: React.FC<{ project: Project; stage: Stage }> = ({ project, stage }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const go = (to: Stage) => navigate(paths.stage(project.id, to));
  const back = () => { const previous = prevStage(stage); navigate(previous ? paths.stage(project.id, previous) : paths.projects()); };
  const update = (updated: Project) => queryClient.setQueryData(["project", project.id], updated);
  /** Every old "approved" / "proceed" callback stored the updated project, then moved to the next screen. */
  const advance = (updated: Project) => { update(updated); const next = nextStage(stage); if (next) go(next); };
  const openEditor = (target: Project) => { update(target); navigate(paths.editor(target.id)); };

  switch (stage) {
    case "acquire": return <AcquisitionScreen project={project} onBack={back} onReviewPages={() => go("pages")} />;
    case "pages": return <PageReviewScreen project={project} onBack={back} onAcquisitionConfirmed={advance} onProceedToPanels={advance} />;
    case "panels": return <PanelReviewScreen project={project} onBack={back} onPanelsApproved={advance} onProceedToOCR={advance} onOpenStoryEditor={openEditor} />;
    case "ocr": return <OCRReviewScreen project={project} onBack={back} onOCRApproved={advance} onProceedToStory={advance} onOpenStoryEditor={openEditor} />;
    case "story": return <StoryReviewScreen project={project} onBack={back} onStoryApproved={advance} onProceedToScript={advance} />;
    case "script": return <ScriptReviewScreen project={project} onBack={back} onScriptApproved={advance} onProceedToAudio={advance} onProjectUpdated={update} />;
    case "audio": return <AudioScreen project={project} onBack={back} onAudioApproved={advance} onProceedToMotion={advance} />;
    case "motion": return <MotionScreen project={project} onBack={back} onMotionApproved={advance} onProceedToRender={advance} />;
    default: return <RenderScreen project={project} onBack={back} onRenderComplete={update} />;
  }
};

export const LegacyStageRoute: React.FC = () => {
  const { id = "", stage = "" } = useParams();
  const navigate = useNavigate();
  const [autoPilotOpen, setAutoPilotOpen] = React.useState(false);
  const query = useQuery({ queryKey: ["project", id], queryFn: () => api.getProject(id), enabled: Boolean(id), retry: false });
  const decision = resolveStageRoute({ id, stage, project: query.data, failed: query.isError });

  if (decision.kind === "redirect") return <Navigate to={decision.to} replace />;
  if (decision.kind === "not-found") {
    return <ErrorState title="This project no longer exists" description="It may have been deleted. Go back to your projects." onBack={() => navigate(paths.projects())} />;
  }
  if (decision.kind === "loading" || !query.data) {
    return <div className="mx-auto grid max-w-7xl gap-4 p-8 grid-cols-1"><Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /></div>;
  }

  const project = query.data;
  return (
    <div className="mx-auto w-full max-w-7xl space-y-5 p-6 md:p-8">
      <PageHeader
        title={project.title}
        actions={<Button variant="secondary" size="sm" icon={<Zap size={14} />} onClick={() => setAutoPilotOpen(true)}>Auto-Pilot</Button>}
      />
      <GlassPanel blur={false} className="p-2.5">
        <PipelineNavbar
          currentStage={project.current_stage}
          currentScreen={stageToNavbarKey(decision.stage)}
          staleStages={project.stale_stages}
          onNavigate={(key) => {
            const target = NAVBAR_KEY_TO_STAGE[key];
            navigate(target === "story_editor" ? paths.editor(project.id) : target ? paths.stage(project.id, target) : paths.projects());
          }}
        />
      </GlassPanel>
      <StageScreen project={project} stage={decision.stage} />
      <AutoPilotModal
        isOpen={autoPilotOpen}
        onClose={() => setAutoPilotOpen(false)}
        project={project}
        onOpenPackaging={() => { setAutoPilotOpen(false); navigate(paths.stage(project.id, "publish")); }}
        onOpenRenderScreen={() => { setAutoPilotOpen(false); navigate(paths.stage(project.id, "render")); }}
        onOpenStage={(stageId) => { setAutoPilotOpen(false); navigate(paths.stage(project.id, AUTOPILOT_STAGE[stageId] ?? "render")); }}
      />
    </div>
  );
};
