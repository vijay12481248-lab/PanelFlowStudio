import React from "react";
import { createHashRouter, redirect, type RouteObject } from "react-router";
import { AppShell } from "./AppShell";
import { SettingsLayout } from "../features/settings/SettingsLayout";
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
      {
        path: "settings",
        element: <SettingsLayout />,
        children: [
          { index: true, loader: () => redirect(paths.settings("engine")) },
          // Engine and Providers keep their old screens until their sections land (M4a tasks 2 and 4).
          { path: "engine", ...legacy("EngineSettingsRoute") },
          { path: "models", ...screen(() => import("../features/settings/SectionPlaceholder"), "SectionPlaceholder") },
          { path: "providers", ...legacy("ProvidersRoute") },
          { path: "youtube", ...screen(() => import("../features/settings/SectionPlaceholder"), "SectionPlaceholder") },
          { path: "diagnostics", ...screen(() => import("../features/settings/SectionPlaceholder"), "SectionPlaceholder") },
          { path: "*", loader: () => redirect(paths.settings("engine")) },
        ],
      },
      { path: "*", loader: toHome },
    ],
  },
];

export const createAppRouter = () => createHashRouter(appRoutes);
