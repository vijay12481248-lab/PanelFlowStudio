import type { Project } from "@panelflow/shared-types";
import { isChronoFlowProject, paths, stageForProject } from "./routes";

export type CommandGroup = "Go to" | "Projects";

export interface Command {
  id: string;
  label: string;
  group: CommandGroup;
  to: string;
  keywords?: string[];
}

type PaletteProject = Pick<Project, "id" | "title" | "current_stage" | "settings" | "source_type">;

const GO_TO: Array<[id: string, label: string, to: string, keywords?: string[]]> = [
  ["home", "Open home", paths.home(), ["inbox", "needs attention"]],
  ["projects", "Open projects", paths.projects()],
  ["create", "Open studios", paths.create(), ["create", "new"]],
  ["create-new", "Create a project", paths.create("new"), ["import", "manga", "pages"]],
  ["create-stories", "Open original stories", paths.create("stories"), ["series", "episodes", "youtube"]],
  ["create-anime", "Open anime review", paths.create("anime")],
  ["create-chronoflow", "Open ChronoFlow", paths.create("chronoflow"), ["h3", "video", "storyboard"]],
  ["create-image", "Create an image", paths.create("image"), ["comfyui", "generate"]],
  ["jobs", "Open jobs", paths.jobs(), ["queue", "running", "failed"]],
  ["library", "Open library", paths.library(), ["audio", "music", "assets"]],
  ["settings-engine", "Open engine settings", paths.settings("engine"), ["health", "tools", "models", "restart"]],
  ["settings-models", "Open model settings", paths.settings("models")],
  ["settings-providers", "Open provider settings", paths.settings("providers"), ["ai", "llm", "ollama"]],
  ["settings-youtube", "Open YouTube settings", paths.settings("youtube"), ["channel", "upload"]],
  ["settings-diagnostics", "Open diagnostics", paths.settings("diagnostics"), ["logs"]],
];

export function buildCommands({ projects }: { projects: PaletteProject[] }): Command[] {
  const navigation: Command[] = GO_TO.map(([id, label, to, keywords]) => ({ id: `go-${id}`, label, group: "Go to", to, keywords }));
  const opens: Command[] = projects.map((project) => ({
    id: `project-${project.id}`,
    label: `Open ${project.title}`,
    group: "Projects",
    to: isChronoFlowProject(project) ? paths.chronoflow({ projectId: project.id }) : paths.stage(project.id, stageForProject(project)),
    keywords: [project.current_stage],
  }));
  return [...navigation, ...opens];
}
