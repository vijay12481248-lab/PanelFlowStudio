import { mount } from "../../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { createMemoryRouter, createStaticHandler, matchRoutes, RouterProvider } from "react-router";
import { SETTINGS_SECTIONS } from "../sections";
import { SettingsLayout } from "../SettingsLayout";
import { appRoutes } from "../../../app/router";

async function mountAt(path: string) {
  const router = createMemoryRouter([{ path: "/settings", element: <SettingsLayout />, children: [{ path: "*", element: <p id="pane">section</p> }] }], { initialEntries: [path] });
  return mount(<RouterProvider router={router} />);
}

test("the section list has five sections in order", async () => {
  const view = await mountAt("/settings/engine");
  const links = [...view.document.querySelectorAll('nav[aria-label="Settings sections"] a')];
  assert.deepEqual(links.map((a) => a.querySelector("[data-section-label]")?.textContent), ["Engine", "Models", "Providers", "YouTube", "Diagnostics"]);
  assert.deepEqual(SETTINGS_SECTIONS.map((s) => s.id), ["engine", "models", "providers", "youtube", "diagnostics"]);
  await view.cleanup();
});

test("only the section you are on is marked current", async () => {
  const view = await mountAt("/settings/providers");
  const current = view.document.querySelectorAll('nav[aria-label="Settings sections"] [aria-current="page"]');
  assert.equal(current.length, 1);
  assert.equal(current[0].querySelector("[data-section-label]")?.textContent, "Providers");
  assert.ok(view.document.getElementById("pane"), "the section renders beside the list");
  await view.cleanup();
});

test("each Settings section has its own route and unknown ones go to Engine", async () => {
  for (const id of ["engine", "models", "providers", "youtube", "diagnostics"]) {
    const matches = matchRoutes(appRoutes, `/settings/${id}`)!;
    assert.ok(matches.some((m) => m.route.element && (m.route.element as React.ReactElement).type === SettingsLayout), `${id} is inside the settings layout`);
    assert.ok(matches.at(-1)!.route.path === id, `${id} has its own child route`);
  }
  for (const url of ["http://localhost/settings", "http://localhost/settings/nope"]) {
    const result = await createStaticHandler(appRoutes).query(new Request(url));
    assert.ok(result instanceof Response && result.headers.get("Location") === "/settings/engine", url);
  }
});
