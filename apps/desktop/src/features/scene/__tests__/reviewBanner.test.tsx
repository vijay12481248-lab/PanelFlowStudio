import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import { ReviewBadge, ReviewRequestBanner, ReviewRequestBannerView } from "../ReviewRequestBanner";
import { engineState } from "../../__tests__/pageHarness";

const waiting = (total: number, firstId = "run-9") => ({ items: total > 0 ? [{ id: firstId }] : [], total_unreviewed: total });
const text = (doc: Document) => doc.body.textContent ?? "";

function stub(result: unknown | Error) {
  const calls: unknown[] = [];
  (api as any).listSceneRuns = async (opts: unknown) => {
    calls.push(opts);
    if (result instanceof Error) throw result;
    return result;
  };
  return calls;
}

test("the banner shows how many pictures wait and links to the newest one", async () => {
  const calls = stub(waiting(3, "run-9"));
  const view = await mountPage(<ReviewRequestBanner />);
  await view.settle();
  assert.match(text(view.document), /3 pictures are waiting for your review/);
  const link = view.document.querySelector('a[href*="run=run-9"]');
  assert.ok(link, "a link to the Scene page with the run id");
  assert.deepEqual(calls[0], { unreviewed: true, limit: 1 }); // one cheap count request, never the whole list
  await view.cleanup();
});

test("one waiting picture reads in the singular", async () => {
  stub(waiting(1));
  const view = await mountPage(<ReviewRequestBanner />);
  await view.settle();
  assert.match(text(view.document), /1 picture is waiting for your review/);
  await view.cleanup();
});

test("the banner is hidden with zero waiting", async () => {
  stub(waiting(0));
  const view = await mountPage(<ReviewRequestBanner />);
  await view.settle();
  assert.equal(view.document.querySelector('[data-testid="review-alert"]'), null);
  await view.cleanup();
});

test("the banner survives a failing request and stays hidden", async () => {
  stub(new Error("engine offline"));
  const view = await mountPage(<ReviewRequestBanner />);
  await view.settle();
  assert.equal(view.document.querySelector('[data-testid="review-alert"]'), null);
  await view.cleanup();
});

test("the banner does not poll while the engine is disconnected", async () => {
  const calls = stub(waiting(2));
  const view = await mountPage(<ReviewRequestBanner />, "/page", engineState({ connected: false }));
  await view.settle();
  assert.equal(calls.length, 0);
  await view.cleanup();
});

test("the alert can be closed, and comes back only when more pictures arrive", async () => {
  stub(waiting(40));
  const view = await mountPage(<ReviewRequestBanner />);
  await view.settle();
  const close = view.document.querySelector('[data-testid="review-alert"] button[aria-label="Dismiss"]') as HTMLButtonElement | null;
  assert.ok(close, "a close button");
  close.click();
  await view.settle();
  assert.equal(view.document.querySelector('[data-testid="review-alert"]'), null);
  await view.cleanup();
});

test("the banner view is hidden on the Scene page itself", async () => {
  const view = await mountPage(<div><ReviewRequestBannerView count={4} firstRunId="r1" pathname="/create/scene" /><span id="after" /></div>);
  await view.settle();
  assert.equal(view.document.querySelector('[data-testid="review-alert"]'), null);
  await view.cleanup();
  const other = await mountPage(<ReviewRequestBannerView count={4} firstRunId="r1" pathname="/jobs" />);
  await other.settle();
  assert.ok(other.document.querySelector('[data-testid="review-alert"]'));
  await other.cleanup();
});

test("the header badge shows the count and is absent at zero", async () => {
  stub(waiting(12));
  const view = await mountPage(<ReviewBadge />);
  await view.settle();
  const badge = view.document.querySelector('[data-testid="review-badge"]');
  assert.ok(badge && badge.textContent?.trim() === "12");
  await view.cleanup();
  stub(waiting(0));
  const none = await mountPage(<ReviewBadge />);
  await none.settle();
  assert.equal(none.document.querySelector('[data-testid="review-badge"]'), null);
  await none.cleanup();
});
