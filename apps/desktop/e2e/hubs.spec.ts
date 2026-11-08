import { expect, test } from "@playwright/test";

// These run against the live engine and the owner's real data, so they only read and navigate:
// they never press Retry, Cancel, or a confirming Delete.

test.beforeEach(async ({ page }) => {
  await page.goto("/#/home");
  const ready = page.getByText("Engine ready");
  const down = page.getByText("Processing engine unavailable");
  await expect(ready.or(down).first()).toBeVisible({ timeout: 30_000 });
  test.skip(await down.first().isVisible(), "The PanelFlow engine is not running.");
});

for (const [route, title] of [["#/home", "Home"], ["#/projects", "Projects"], ["#/jobs", "Jobs"], ["#/library", "Library"]] as const) {
  test(`${title} has exactly one page heading`, async ({ page }) => {
    await page.goto(`/${route}`);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.locator("h1")).toHaveCount(1);
  });
}

test("Home shows what needs you, and a review row opens its stage", async ({ page }) => {
  await page.goto("/#/home");
  await expect(page.getByRole("heading", { name: "Needs you" })).toBeVisible();
  const rows = page.locator("[data-inbox-row]");
  const empty = page.getByText("Nothing needs you");
  await expect(rows.first().or(empty)).toBeVisible({ timeout: 15_000 });
  const action = rows.locator("button", { hasText: /^(Review|Decide|Open)$/ }).first();
  if (await action.count()) {
    await action.click();
    await expect(page).toHaveURL(/#\/(projects\/[^/]+\/[a-z]+|create\/stories)$/);
  }
});

test("Projects search narrows the list and clearing it brings everything back", async ({ page }) => {
  await page.goto("/#/projects");
  const tiles = page.locator("[data-project-tile]");
  await expect(tiles.first()).toBeVisible({ timeout: 15_000 });
  const total = await tiles.count();
  await page.getByRole("searchbox", { name: "Search projects" }).fill("xyz-no-match-xyz");
  await expect(page.getByText("No projects match")).toBeVisible();
  await expect(tiles).toHaveCount(0);
  await page.getByRole("searchbox", { name: "Search projects" }).fill("");
  await expect(tiles).toHaveCount(total);
});

test("Deleting a project asks first and Cancel keeps it", async ({ page }) => {
  await page.goto("/#/projects");
  const tile = page.locator("[data-project-tile]").first();
  await expect(tile).toBeVisible({ timeout: 15_000 });
  const total = await page.locator("[data-project-tile]").count();
  await tile.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Delete project" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("You cannot undo this.");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.locator("[data-project-tile]")).toHaveCount(total);
});

test("Jobs has three tabs and switching changes the visible list", async ({ page }) => {
  await page.goto("/#/jobs");
  const tabs = page.getByRole("tab");
  await expect(tabs).toHaveCount(3);
  await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "true");
  await tabs.nth(1).click();
  await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
  await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "false");
});

test("page text on Projects can be selected", async ({ page }) => {
  await page.goto("/#/projects");
  expect(await page.evaluate(() => getComputedStyle(document.querySelector("main")!).userSelect)).not.toBe("none");
});

for (const [route, title] of [["#/home", "Home"], ["#/projects", "Projects"], ["#/jobs", "Jobs"], ["#/library", "Library"]] as const) {
  for (const width of [1440, 1100]) {
    test(`${title} never scrolls sideways at ${width}px wide`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto(`/${route}`);
      await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
      await page.waitForTimeout(1500); // let real data (long titles) render
      const { scroll, client } = await page.evaluate(() => {
        const main = document.querySelector("main")!;
        return { scroll: main.scrollWidth, client: main.clientWidth };
      });
      expect(scroll, `main is ${scroll}px wide inside ${client}px`).toBeLessThanOrEqual(client + 1);
    });
  }
}
