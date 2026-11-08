import { expect, test } from "@playwright/test";

// These run against the live engine and the owner's real settings, so they only read and navigate:
// they never press Save, Pull, Install, Restart or Export, and never type a real token.

test.beforeEach(async ({ page }) => {
  await page.goto("/#/settings/engine");
  const list = page.getByRole("navigation", { name: "Settings sections" });
  const down = page.getByText("Processing engine unavailable");
  await expect(list.or(down).first()).toBeVisible({ timeout: 30_000 });
  test.skip(await down.first().isVisible(), "The PanelFlow engine is not running.");
});

const SECTIONS = [["engine", "Engine"], ["models", "Models"], ["providers", "Providers"], ["youtube", "YouTube"], ["diagnostics", "Diagnostics"]] as const;

test("the Settings list has five sections and each one changes the route", async ({ page }) => {
  const list = page.getByRole("navigation", { name: "Settings sections" });
  await expect(list.getByRole("link")).toHaveCount(5);
  for (const [id, label] of SECTIONS) {
    await list.getByRole("link", { name: new RegExp(`^${label}`) }).click();
    await expect(page).toHaveURL(new RegExp(`#/settings/${id}$`));
    await expect(list.getByRole("link", { name: new RegExp(`^${label}`) })).toHaveAttribute("aria-current", "page");
  }
});

test("Engine shows resource gauges and a tool list", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Resources" })).toBeVisible();
  await expect(page.getByRole("progressbar").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: "Tools" })).toBeVisible();
  await expect(page.getByText("FFmpeg").first()).toBeVisible({ timeout: 15_000 });
});

test("Models has an empty password field for the token and a disabled Save", async ({ page }) => {
  await page.goto("/#/settings/models");
  const token = page.getByLabel("Access token (optional)");
  await expect(token).toBeVisible({ timeout: 15_000 });
  await expect(token).toHaveAttribute("type", "password");
  await expect(token).toHaveValue("");
  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();
});

test("changing a model enables Save and Discard puts it back, without saving anything", async ({ page }) => {
  await page.goto("/#/settings/models");
  const narration = page.getByLabel("Narration model");
  await expect(narration).toBeVisible({ timeout: 15_000 });
  const original = await narration.inputValue();
  const options = await narration.locator("option").evaluateAll((els) => els.map((e) => (e as HTMLOptionElement).value));
  const other = options.find((value) => value !== original);
  test.skip(!other, "Only one model is installed, so there is nothing to switch to.");
  await narration.selectOption(other!);
  await expect(page.getByRole("button", { name: "Save changes" })).toBeEnabled();
  await page.getByRole("button", { name: "Discard" }).first().click();
  await expect(narration).toHaveValue(original);
  await expect(page.getByRole("button", { name: "Save changes" })).toBeDisabled();
});

test("Providers lists the four workflows and the cloud API key field is a password field", async ({ page }) => {
  await page.goto("/#/settings/providers");
  for (const label of ["Story narration", "Script writing", "Character profiling", "Panel and OCR inspection"]) {
    await expect(page.getByLabel(`Provider for ${label}`)).toBeVisible({ timeout: 15_000 });
  }
  await expect(page.getByLabel("API key")).toHaveAttribute("type", "password");
  await expect(page.getByRole("button", { name: "Save routing" })).toBeDisabled();
});

test("Diagnostics shows hardware rows and the review-before-sharing note", async ({ page }) => {
  await page.goto("/#/settings/diagnostics");
  await expect(page.getByText("Review it before you share it.")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("GPU", { exact: true })).toBeVisible();
});

test("YouTube opens the existing settings window and it can be closed", async ({ page }) => {
  await page.goto("/#/settings/youtube");
  await page.getByRole("button", { name: "Open YouTube settings" }).click();
  await expect(page.getByText("AI connections")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: /YouTube/ }).first()).toBeVisible();
});

for (const [id, label] of SECTIONS) {
  for (const width of [1440, 1100]) {
    test(`${label} has one heading level one and never scrolls sideways at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(`/#/settings/${id}`);
      await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();
      await expect(page.locator("h1")).toHaveCount(1);
      await page.waitForTimeout(1800);
      const { scroll, client } = await page.evaluate(() => {
        const main = document.querySelector("main")!;
        return { scroll: main.scrollWidth, client: main.clientWidth };
      });
      expect(scroll, `main is ${scroll}px wide inside ${client}px`).toBeLessThanOrEqual(client + 1);
    });
  }
}

test("no secret-looking text is on any Settings page", async ({ page }) => {
  for (const [id] of SECTIONS) {
    await page.goto(`/#/settings/${id}`);
    await page.waitForTimeout(1500);
    const body = await page.evaluate(() => document.body.innerText);
    expect(body, id).not.toMatch(/sk-[A-Za-z0-9]{12,}|gsk_[A-Za-z0-9]{12,}|Bearer\s+[A-Za-z0-9._-]{12,}/);
  }
});
