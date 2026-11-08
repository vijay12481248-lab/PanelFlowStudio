import React from "react";
import { createHashRouter, redirect, type RouteObject } from "react-router";
import { AppShell } from "./AppShell";
import { paths } from "./routes";

/** Screens load on demand: the editor alone pulls in a large dependency tree. */
const screen = (load: () => Promise<Record<string, any>>, name: string): Pick<RouteObject, "lazy"> => ({
  lazy: async () => ({ Component: (await load())[name] as React.ComponentType }),
});
const legacy = (name: string) => screen(() => import("../features/legacy/LegacyScreens"), name);
const toHome = () => redirect(paths.home());

export const appRoutes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, loader: toHome },
      { path: "home", ...screen(() => import("../features/home/HomePage"), "HomePage") },
      { path: "projects", ...screen(() => import("../features/projects/ProjectsPage"), "ProjectsPage") },
      { path: "projects/:id", ...legacy("ProjectRedirect") },
      { path: "projects/:id/:stage", ...screen(() => import("../features/legacy/LegacyStageRoute"), "LegacyStageRoute") },
      { path: "editor/:id", ...legacy("EditorRoute") },
      { path: "create", ...screen(() => import("../features/create/CreateIndex"), "CreateIndex") },
      { path: "create/new", ...legacy("NewProjectRoute") },
      { path: "create/stories", ...legacy("StoriesRoute") },
      { path: "create/anime", ...legacy("AnimeRoute") },
      { path: "create/image", ...legacy("ImageRoute") },
      { path: "create/chronoflow", ...legacy("ChronoFlowRoute") },
      { path: "create/chronoflow/job/:jobId", ...legacy("ChronoFlowRoute") },
      { path: "create/chronoflow/:projectId", ...legacy("ChronoFlowRoute") },
      { path: "jobs", ...screen(() => import("../features/jobs/JobsPage"), "JobsPage") },
      { path: "library", ...screen(() => import("../features/library/LibraryPage"), "LibraryPage") },
      { path: "library/*", ...screen(() => import("../features/library/LibraryPage"), "LibraryPage") },
      { path: "settings", loader: () => redirect(paths.settings("engine")) },
      { path: "settings/engine", ...legacy("EngineSettingsRoute") },
      { path: "settings/providers", ...legacy("ProvidersRoute") },
      { path: "settings/*", loader: () => redirect(paths.settings("engine")) },
      { path: "*", loader: toHome },
    ],
  },
];

export const createAppRouter = () => createHashRouter(appRoutes);
