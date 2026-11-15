import { mount } from "../../../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { Project } from "@panelflow/shared-types";
import type { Stage } from "../../../../app/routes";
import { useStageNav } from "../useStageNav";

const project = { id: "p1", title: "Dawn Gate" } as Project;

async function setup(stage: Stage) {
  let nav!: ReturnType<typeof useStageNav>;
  const Probe: React.FC = () => { nav = useStageNav(project, stage); return <p>probe</p>; };
  const client = new QueryClient();
  const router = createMemoryRouter([{ path: "*", element: <Probe /> }], { initialEntries: [`/projects/p1/${stage}`] });
  const view = await mount(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
  return { nav: () => nav, router, client, view };
}

test("advance stores the updated project and moves to the next stage", async () => {
  const { nav, router, client, view } = await setup("pages");
  const updated = { ...project, title: "Updated" } as Project;
  await act(async () => { nav().advance(updated); });
  assert.equal((client.getQueryData(["project", "p1"]) as Project).title, "Updated");
  assert.equal(router.state.location.pathname, "/projects/p1/panels");
  await view.cleanup();
  client.clear();
});

test("back from the first stage goes to the projects list, otherwise to the previous stage", async () => {
  const first = await setup("acquire");
  await act(async () => { first.nav().back(); });
  assert.equal(first.router.state.location.pathname, "/projects");
  await first.view.cleanup();
  const second = await setup("audio");
  await act(async () => { second.nav().back(); });
  assert.equal(second.router.state.location.pathname, "/projects/p1/script");
  await second.view.cleanup();
  first.client.clear(); second.client.clear();
});

test("goTo opens the named stage", async () => {
  const { nav, router, client, view } = await setup("acquire");
  await act(async () => { nav().goTo("pages"); });
  assert.equal(router.state.location.pathname, "/projects/p1/pages");
  await view.cleanup();
  client.clear();
});
