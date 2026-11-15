import React from "react";
import { Icons } from "@panelflow/ui";

export type WorkflowStepId = 1 | 2 | 3 | 4 | 5 | 6 | 7;

interface WorkflowStepperRibbonProps {
  currentStep: WorkflowStepId;
  onSelectStep: (step: WorkflowStepId) => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const WorkflowStepperRibbon: React.FC<WorkflowStepperRibbonProps> = ({
  currentStep,
  onSelectStep,
  collapsed: externalCollapsed,
  onToggleCollapse,
}) => {
  const [internalCollapsed, setInternalCollapsed] = React.useState<boolean>(false);
  const isCollapsed = externalCollapsed ?? internalCollapsed;
  const toggleCollapse = onToggleCollapse ?? (() => setInternalCollapsed((c) => !c));
  const steps: Array<{
    id: WorkflowStepId;
    title: string;
    description: string;
    color: string;
    borderColor: string;
    bgAccent: string;
    icon: React.ReactNode;
  }> = [
    {
      id: 1,
      title: "Import Manga",
      description: "Import manga pages or folder",
      color: "text-info",
      borderColor: "border-accent/40",
      bgAccent: "from-accent/40 to-ink",
      icon: <Icons.BookOpen className="w-3.5 h-3.5 text-info" />,
    },
    {
      id: 2,
      title: "Select Panels",
      description: "Auto detect or manually select panels",
      color: "text-info",
      borderColor: "border-info/40",
      bgAccent: "from-info/40 to-ink",
      icon: <Icons.Layout className="w-3.5 h-3.5 text-info" />,
    },
    {
      id: 3,
      title: "Arrange Story",
      description: "Drag panels to timeline and arrange",
      color: "text-ok",
      borderColor: "border-ok/40",
      bgAccent: "from-ok/40 to-ink",
      icon: <Icons.Layers className="w-3.5 h-3.5 text-ok" />,
    },
    {
      id: 4,
      title: "Edit Motion & Effects",
      description: "Apply motion presets or customize",
      color: "text-warn",
      borderColor: "border-warn/40",
      bgAccent: "from-warn/40 to-ink",
      icon: <Icons.Sparkles className="w-3.5 h-3.5 text-warn" />,
    },
    {
      id: 5,
      title: "Add Narration",
      description: "Edit script, select voice and adjust timing",
      color: "text-bad",
      borderColor: "border-bad/40",
      bgAccent: "from-bad/40 to-ink",
      icon: <Icons.MessageSquare className="w-3.5 h-3.5 text-bad" />,
    },
    {
      id: 6,
      title: "Add Music & SFX",
      description: "Add background music and sound effects",
      color: "text-info",
      borderColor: "border-accent/40",
      bgAccent: "from-accent/40 to-ink",
      icon: <Icons.Music className="w-3.5 h-3.5 text-info" />,
    },
    {
      id: 7,
      title: "Preview & Export",
      description: "Preview final video and export",
      color: "text-info",
      borderColor: "border-accent/40",
      bgAccent: "from-accent/40 to-ink",
      icon: <Icons.Film className="w-3.5 h-3.5 text-info" />,
    },
  ];

  if (isCollapsed) {
    const activeStepObj = steps.find((s) => s.id === currentStep) || steps[0];
    return (
      <div className="h-7 bg-ink/95 border-t border-edge/80 px-3 flex items-center justify-between select-none shrink-0 z-20 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold text-fg-faint uppercase tracking-wider">
            Workflow:
          </span>
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-navy border border-edge">
            <span className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] font-bold font-mono bg-ink border ${activeStepObj.borderColor} ${activeStepObj.color}`}>
              {activeStepObj.id}
            </span>
            <span className="text-[11px] font-bold text-fg">
              {activeStepObj.title}
            </span>
            <span className="text-[10px] text-fg-faint hidden sm:inline">
              — {activeStepObj.description}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={toggleCollapse}
          className="flex items-center gap-1 text-[11px] text-fg-dim hover:text-fg px-2 py-0.5 rounded hover:bg-navy transition-colors"
          title="Show all workflow steps"
        >
          <span>Show Steps</span>
          <Icons.ChevronDown className="w-3.5 h-3.5 rotate-180" />
        </button>
      </div>
    );
  }

  return (
    <div className="h-14 bg-ink/95 border-t border-edge/80 px-3 py-1 flex items-center justify-between gap-1.5 select-none overflow-x-auto shrink-0 z-20">
      <div className="flex-1 flex items-center justify-between gap-1.5 min-w-0">
        {steps.map((step, idx) => {
          const isActive = currentStep === step.id;
          return (
            <React.Fragment key={step.id}>
              <button
                type="button"
                onClick={() => onSelectStep(step.id)}
                className={`flex-1 min-w-[130px] max-w-[210px] h-full rounded-lg px-2.5 py-1 text-left border transition-all flex flex-col justify-center bg-gradient-to-b ${step.bgAccent} ${
                  isActive
                    ? `${step.borderColor} ring-1 ring-white/20 shadow-md scale-[1.02]`
                    : "border-edge/80 hover:border-edge opacity-75 hover:opacity-100"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold font-mono bg-navy border ${step.borderColor} ${step.color}`}>
                    {step.id}
                  </span>
                  <span className="text-[11px] font-bold text-fg truncate">
                    {step.title}
                  </span>
                </div>
                <span className="text-[9px] text-fg-dim truncate block mt-0.5 pl-5.5">
                  {step.description}
                </span>
              </button>

              {idx < steps.length - 1 && (
                <Icons.ChevronDown className="w-3 h-3 -rotate-90 text-ink shrink-0" />
              )}
            </React.Fragment>
          );
        })}
      </div>

      <button
        type="button"
        onClick={toggleCollapse}
        className="p-1.5 rounded-lg text-fg-faint hover:text-fg-dim hover:bg-navy transition-colors shrink-0 ml-1"
        title="Hide workflow steps"
      >
        <Icons.ChevronDown className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};
