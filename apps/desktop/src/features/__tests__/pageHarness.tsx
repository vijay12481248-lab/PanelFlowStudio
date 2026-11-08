import { mount } from "../../../../../packages/ui/src/v2/__tests__/dom"; // installs jsdom before Radix loads
import React from "react";
import { after } from "node:test";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@panelflow/ui-v2";
import { ErrorProvider } from "../../context/ErrorContext";
import { EngineContext, type EngineState } from "../../app/providers";

export const engineState = (overrides: Partial<EngineState> = {}): EngineState => ({
  connected: true, version: "1.0.0-beta.2", startupGrace: false, retrying: false, restarting: false, retry: async () => {}, restart: async () => {}, ...overrides,
});

/** Mount a page the way the app does (router, query cache, engine, errors, toasts), in jsdom. */
export async function mountPage(element: React.ReactElement, path = "/page") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [{ path: "/page", element }, { path: "*", element: <p id="elsewhere">elsewhere</p> }],
    { initialEntries: [path] },
  );
  const view = await mount(
    <ErrorProvider>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <EngineContext.Provider value={engineState()}><RouterProvider router={router} /></EngineContext.Provider>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorProvider>,
  );
  /** Wait until queued promises and React Query have settled: no loading skeleton left (or 2 seconds). */
  const settle = async () => {
    for (let i = 0; i < 80; i++) {
      await new Promise((resolve) => setTimeout(resolve, 25));
      if (i >= 3 && !view.document.querySelector('[class*="animate-pulse"]')) return;
    }
  };
  return { ...view, router, client, settle, cleanup: async () => { await view.cleanup(); client.clear(); } };
}

// React Query polling and Radix leave timers behind in jsdom, which would keep this test process alive for a minute.
// The unref'd timer fires only if something else is holding the process open, and keeps the real exit code.
after(() => { setTimeout(() => process.exit(process.exitCode ?? 0), 300).unref(); });
