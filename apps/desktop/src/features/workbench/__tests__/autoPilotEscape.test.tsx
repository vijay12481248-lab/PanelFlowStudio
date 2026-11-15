import { mount } from "../../../../../../packages/ui/src/v2/__tests__/dom"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { AutoPilotModal } from "../../../components/AutoPilotModal";

const project = { id: "p1", title: "Dawn Gate", current_stage: "NEW", settings: {}, source_type: "MANGA", rights_status: "AUTHORIZED_WEB", stale_stages: [] } as unknown as Project;

function setup() {
  (api as any).getAutoPilotStatus = async () => { throw new Error("offline"); }; // the modal tolerates a failed poll
  (Element.prototype as any).scrollIntoView = () => {};
}
const press = (key: string) => act(async () => { document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true })); });

test("Escape closes the Auto-Pilot dialog once, so it can be dismissed from the keyboard", async () => {
  setup();
  let closed = 0;
  const view = await mount(<AutoPilotModal isOpen onClose={() => { closed++; }} project={project} />);
  assert.ok(view.document.querySelector('[role="dialog"]'));
  await press("Escape");
  assert.equal(closed, 1);
  await press("Enter");
  assert.equal(closed, 1, "other keys do nothing");
  await view.cleanup();
});

test("a closed Auto-Pilot dialog ignores Escape", async () => {
  setup();
  let closed = 0;
  const view = await mount(<AutoPilotModal isOpen={false} onClose={() => { closed++; }} project={project} />);
  await press("Escape");
  assert.equal(closed, 0);
  await view.cleanup();
});
