import { expect, test, type Page } from "@playwright/test";

const dock = (page: Page) => page.getByRole("navigation", { name: "Main" });

test.beforeEach(async ({ page }) => {
  await page.goto("/#/home");
  const ready = page.getByText("Engine ready");
  // "Connecting" is a transient state at launch; only a settled "unavailable" means the engine is down.
  const notReady = page.getByText("Processing engine unavailable");
  await expect(ready.or(notReady).first()).toBeVisible({ timeout: 30_000 });
  test.skip(await notReady.first().isVisible(), "The PanelFlow engine is not running, so the shell cannot render pages.");
});

test("the dock has six destinations and each one changes the route", async ({ page }) => {
  const expected: Array<[string, RegExp]> = [
    ["Projects", /#\/projects$/], ["Create", /#\/create$/], ["Jobs", /#\/jobs$/],
    ["Library", /#\/library$/], ["Settings", /#\/settings\/engine$/], ["Home", /#\/home$/],
  ];
  await expect(dock(page).getByRole("link")).toHaveCount(6);
  for (const [name, route] of expected) {
    await dock(page).getByRole("link", { name }).click();
    await expect(page).toHaveURL(route);
    await expect(dock(page).getByRole("link", { name })).toHaveAttribute("aria-current", "page");
  }
});

test("the browser back button returns to the previous screen", async ({ page }) => {
  await dock(page).getByRole("link", { name: "Jobs" }).click();
  await expect(page).toHaveURL(/#\/jobs$/);
  await dock(page).getByRole("link", { name: "Create" }).click();
  await expect(page).toHaveURL(/#\/create$/);
  await page.goBack();
  await expect(page).toHaveURL(/#\/jobs$/);
});

test("Ctrl K opens the palette, finds a screen and goes there", async ({ page }) => {
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Go anywhere" });
  await expect(palette).toBeVisible();
  await page.keyboard.type("original");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/create\/stories$/);
  await expect(palette).toBeHidden();
});

test("Escape closes the palette and returns focus to the button that opened it", async ({ page }) => {
  const trigger = page.getByRole("button", { name: /Open command palette/ });
  await trigger.click();
  await expect(page.getByRole("dialog", { name: "Go anywhere" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Go anywhere" })).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("a project that does not exist shows a way back instead of a blank page", async ({ page }) => {
  await page.goto("/#/projects/nope/ocr");
  await expect(page.getByText("This project no longer exists")).toBeVisible();
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(page).toHaveURL(/#\/projects$/);
});

test("an unknown address lands on Home", async ({ page }) => {
  await page.goto("/#/this-does-not-exist");
  await expect(page).toHaveURL(/#\/home$/);
});

test("page text can be selected and copied", async ({ page }) => {
  const userSelect = await page.evaluate(() => getComputedStyle(document.body).userSelect);
  expect(userSelect).not.toBe("none");
});
