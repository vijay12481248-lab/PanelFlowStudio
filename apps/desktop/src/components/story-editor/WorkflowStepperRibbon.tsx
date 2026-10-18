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
      color: "text-blue-400",
      borderColor: "border-blue-500/40",
      bgAccent: "from-blue-950/40 to-zinc-950",
      icon: <Icons.BookOpen className="w-3.5 h-3.5 text-blue-400" />,
    },
    {
      id: 2,
      title: "Select Panels",
      description: "Auto detect or manually select panels",
      color: "text-cyan-400",
      borderColor: "border-cyan-500/40",
      bgAccent: "from-cyan-950/40 to-zinc-950",
      icon: <Icons.Layout className="w-3.5 h-3.5 text-cyan-400" />,
    },
    {
      id: 3,
      title: "Arrange Story",
      description: "Drag panels to timeline and arrange",
      color: "text-emerald-400",
      borderColor: "border-emerald-500/40",
      bgAccent: "from-emerald-950/40 to-zinc-950",
      icon: <Icons.Layers className="w-3.5 h-3.5 text-emerald-400" />,
    },
    {
      id: 4,
      title: "Edit Motion & Effects",
      description: "Apply motion presets or customize",
      color: "text-amber-400",
      borderColor: "border-amber-500/40",
      bgAccent: "from-amber-950/40 to-zinc-950",
      icon: <Icons.Sparkles className="w-3.5 h-3.5 text-amber-400" />,
    },
    {
      id: 5,
      title: "Add Narration",
      description: "Edit script, select voice and adjust timing",
      color: "text-rose-400",
      borderColor: "border-rose-500/40",
      bgAccent: "from-rose-950/40 to-zinc-950",
      icon: <Icons.MessageSquare className="w-3.5 h-3.5 text-rose-400" />,
    },
    {
      id: 6,
      title: "Add Music & SFX",
      description: "Add background music and sound effects",
      color: "text-purple-400",
      borderColor: "border-purple-500/40",
      bgAccent: "from-purple-950/40 to-zinc-950",
      icon: <Icons.Music className="w-3.5 h-3.5 text-purple-400" />,
    },
    {
      id: 7,
      title: "Preview & Export",
      description: "Preview final video and export",
      color: "text-indigo-400",
      borderColor: "border-indigo-500/40",
      bgAccent: "from-indigo-950/40 to-zinc-950",
      icon: <Icons.Film className="w-3.5 h-3.5 text-indigo-400" />,
    },
  ];

  if (isCollapsed) {
    const activeStepObj = steps.find((s) => s.id === currentStep) || steps[0];
    return (
      <div className="h-7 bg-zinc-950/95 border-t border-zinc-800/80 px-3 flex items-center justify-between select-none shrink-0 z-20 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">
            Workflow:
          </span>
          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800">
            <span className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] font-bold font-mono bg-zinc-950 border ${activeStepObj.borderColor} ${activeStepObj.color}`}>
              {activeStepObj.id}
            </span>
            <span className="text-[11px] font-bold text-zinc-200">
              {activeStepObj.title}
            </span>
            <span className="text-[10px] text-zinc-500 hidden sm:inline">
              — {activeStepObj.description}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={toggleCollapse}
          className="flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200 px-2 py-0.5 rounded hover:bg-zinc-900 transition-colors"
          title="Show all workflow steps"
        >
          <span>Show Steps</span>
          <Icons.ChevronDown className="w-3.5 h-3.5 rotate-180" />
        </button>
      </div>
    );
  }

  return (
    <div className="h-14 bg-zinc-950/95 border-t border-zinc-800/80 px-3 py-1 flex items-center justify-between gap-1.5 select-none overflow-x-auto shrink-0 z-20">
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
                    : "border-zinc-800/80 hover:border-zinc-700 opacity-75 hover:opacity-100"
                }`}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold font-mono bg-zinc-900 border ${step.borderColor} ${step.color}`}>
                    {step.id}
                  </span>
                  <span className="text-[11px] font-bold text-zinc-100 truncate">
                    {step.title}
                  </span>
                </div>
                <span className="text-[9px] text-zinc-400 truncate block mt-0.5 pl-5.5">
                  {step.description}
                </span>
              </button>

              {idx < steps.length - 1 && (
                <Icons.ChevronDown className="w-3 h-3 -rotate-90 text-zinc-700 shrink-0" />
              )}
            </React.Fragment>
          );
        })}
      </div>

      <button
        type="button"
        onClick={toggleCollapse}
        className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900 transition-colors shrink-0 ml-1"
        title="Hide workflow steps"
      >
        <Icons.ChevronDown className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};
