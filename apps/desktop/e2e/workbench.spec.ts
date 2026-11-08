import { expect, test, type Page } from "@playwright/test";

// These run against the live engine and the owner's real projects, so they only read and navigate:
// they never press Approve, Retry, Get or Refresh packaging, or Start in Auto-Pilot.

const STAGES = ["acquire", "pages", "panels", "ocr", "story", "script", "audio", "motion", "render", "publish"] as const;
const LABELS = ["Source", "Pages", "Panels", "OCR", "Story", "Script", "Audio", "Motion", "Render", "Publish"];

test.beforeEach(async ({ page }) => {
  await page.goto("/#/home");
  const ready = page.getByText("Engine ready");
  const down = page.getByText("Processing engine unavailable");
  await expect(ready.or(down).first()).toBeVisible({ timeout: 30_000 });
  test.skip(await down.first().isVisible(), "The PanelFlow engine is not running.");
});

/** The first project that opens a pipeline stage (ChronoFlow projects open a different studio). */
async function firstPipelineProject(page: Page): Promise<string> {
  await page.goto("/#/projects");
  const tiles = page.locator("[data-project-tile] > button");
  await expect(tiles.first()).toBeVisible({ timeout: 15_000 });
  const count = await tiles.count();
  for (let i = 0; i < count; i++) {
    await page.goto("/#/projects");
    await expect(tiles.nth(i)).toBeVisible();
    await tiles.nth(i).click();
    await page.waitForTimeout(600);
    const match = /#\/projects\/([^/]+)\/[a-z]+$/.exec(page.url());
    if (match) return match[1];
  }
  test.skip(true, "No pipeline project exists.");
  return "";
}

test("every stage has exactly one page heading and the full stepper", async ({ page }) => {
  const id = await firstPipelineProject(page);
  for (const stage of STAGES) {
    await page.goto(`/#/projects/${id}/${stage}`);
    await expect(page.getByRole("list", { name: "Pipeline stages" }).getByRole("listitem")).toHaveCount(10, { timeout: 15_000 });
    await page.waitForTimeout(800);
    await expect(page.locator("h1"), `${stage} has more than one h1`).toHaveCount(1);
    const labels = await page.getByRole("list", { name: "Pipeline stages" }).getByRole("listitem").evaluateAll((els) => els.map((e) => (e.textContent ?? "").split(":")[0].replace(/(Stale|Blocked)$/, "")));
    expect(labels).toEqual(LABELS);
  }
});

for (const width of [1440, 1100]) {
  test(`no stage scrolls sideways at ${width}px wide`, async ({ page }) => {
    const id = await firstPipelineProject(page);
    await page.setViewportSize({ width, height: 800 });
    for (const stage of STAGES) {
      await page.goto(`/#/projects/${id}/${stage}`);
      await expect(page.getByRole("list", { name: "Pipeline stages" })).toBeVisible({ timeout: 15_000 });
      await page.waitForTimeout(1200);
      const { scroll, client } = await page.evaluate(() => {
        const main = document.querySelector("main")!;
        return { scroll: main.scrollWidth, client: main.clientWidth };
      });
      expect(scroll, `${stage}: main is ${scroll}px wide inside ${client}px`).toBeLessThanOrEqual(client + 1);
    }
  });
}

test("a stepper link can be reached and followed from the keyboard", async ({ page }) => {
  const id = await firstPipelineProject(page);
  await page.goto(`/#/projects/${id}/ocr`);
  const first = page.getByRole("list", { name: "Pipeline stages" }).getByRole("link").first();
  await expect(first).toBeVisible({ timeout: 15_000 });
  await first.focus();
  await expect(first).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`#/projects/${id}/acquire$`));
});

test("there is one Auto-Pilot button; it opens and Escape closes it", async ({ page }) => {
  const id = await firstPipelineProject(page);
  await page.goto(`/#/projects/${id}/publish`);
  const buttons = page.getByRole("button", { name: "Auto-Pilot", exact: true });
  await expect(buttons).toHaveCount(1, { timeout: 15_000 });
  await buttons.click();
  await expect(page.getByText("1-Click End-to-End")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("1-Click End-to-End")).toBeHidden();
});

test("Open story editor goes to the editor for this project", async ({ page }) => {
  const id = await firstPipelineProject(page);
  await page.goto(`/#/projects/${id}/ocr`);
  await page.getByRole("link", { name: "Open story editor" }).click();
  await expect(page).toHaveURL(new RegExp(`#/editor/${id}$`));
});

test("Publish shows the checks and waits for a button before asking for packaging", async ({ page }) => {
  const id = await firstPipelineProject(page);
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto(`/#/projects/${id}/publish`);
  await expect(page.getByRole("heading", { name: "Before you upload" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("PanelFlow does not upload pipeline videos yet.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Get packaging" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Upload now|Publish now|Schedule/ })).toHaveCount(0);
  await page.waitForTimeout(1500);
  expect(requests.filter((url) => url.includes("/youtube/packaging")), "packaging was requested without a button press").toEqual([]);
});
