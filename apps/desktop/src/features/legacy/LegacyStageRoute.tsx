import React from "react";
import { Navigate, useNavigate, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { ErrorState, Skeleton } from "@panelflow/ui-v2";
import { OCRReviewScreen } from "../../screens/OCRReviewScreen";
import { AutoPilotModal } from "../../components/AutoPilotModal";
import { paths, type Stage } from "../../app/routes";
import { useStageNav } from "../stages/kit/useStageNav";
import { AcquireStage } from "../stages/acquire/AcquireStage";
import { PagesStage } from "../stages/pages/PagesStage";
import { PanelsStage } from "../stages/panels/PanelsStage";
import { MotionStage } from "../stages/motion/MotionStage";
import { AudioStage } from "../stages/audio/AudioStage";
import { StoryStage } from "../stages/story/StoryStage";
import { ScriptStage } from "../stages/script/ScriptStage";
import { RenderStage } from "../stages/render/RenderStage";
import { PublishStage } from "../workbench/PublishStage";
import { WorkbenchFrame } from "../workbench/WorkbenchFrame";
import { resolveStageRoute } from "./resolveStageRoute";

/** AutoPilotModal speaks in its own stage ids; translate them to routes. */
const AUTOPILOT_STAGE: Record<string, Stage> = {
  pages: "pages", panels: "panels", ocr: "ocr", story: "story", script: "script", audio: "audio", motion: "motion", render: "render", packaging: "publish",
};

const StageScreen: React.FC<{ project: Project; stage: Stage }> = ({ project, stage }) => {
  const navigate = useNavigate();
  const { goTo: go, back, store: update, advance } = useStageNav(project, stage);
  const openEditor = (target: Project) => { update(target); navigate(paths.editor(target.id)); };

  switch (stage) {
    case "acquire": return <AcquireStage project={project} onReviewPages={() => go("pages")} />;
    case "pages": return <PagesStage project={project} onConfirmed={advance} onContinue={advance} />;
    case "panels": return <PanelsStage project={project} onConfirmed={advance} onContinue={advance} onOpenStoryEditor={openEditor} />;
    case "ocr": return <OCRReviewScreen project={project} onBack={back} onOCRApproved={advance} onProceedToStory={advance} onOpenStoryEditor={openEditor} />;
    case "story": return <StoryStage project={project} onApproved={advance} onContinue={advance} />;
    case "script": return <ScriptStage project={project} onApproved={advance} onContinue={advance} onProjectUpdated={update} />;
    case "audio": return <AudioStage project={project} onApproved={advance} onContinue={advance} />;
    case "motion": return <MotionStage project={project} onApproved={advance} onContinue={advance} />;
    case "publish": return <PublishStage project={project} />;
    default: return <RenderStage project={project} onRenderComplete={update} />;
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
    <WorkbenchFrame project={project} stage={decision.stage} onAutoPilot={() => setAutoPilotOpen(true)}>
      <StageScreen project={project} stage={decision.stage} />
      <AutoPilotModal
        isOpen={autoPilotOpen}
        onClose={() => setAutoPilotOpen(false)}
        project={project}
        onOpenPackaging={() => { setAutoPilotOpen(false); navigate(paths.stage(project.id, "publish")); }}
        onOpenRenderScreen={() => { setAutoPilotOpen(false); navigate(paths.stage(project.id, "render")); }}
        onOpenStage={(stageId) => { setAutoPilotOpen(false); navigate(paths.stage(project.id, AUTOPILOT_STAGE[stageId] ?? "render")); }}
      />
    </WorkbenchFrame>
  );
};
