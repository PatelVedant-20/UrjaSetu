import { test, expect } from "@playwright/test";
test("all feature routes render without errors or page overflow", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const route of [
    "/",
    "/market",
    "/trades",
    "/energy",
    "/forecasts",
    "/grid",
    "/community",
    "/settlements",
    "/audit",
    "/settings",
  ]) {
    await page.goto(route);
    await expect(page.locator("h1")).toBeVisible();
    await expect(
      page.getByText("Illustrative demo", { exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  expect(errors).toEqual([]);
});
test("market drafts stay local and show feedback", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST") writes.push(r.url());
  });
  await page.goto("/market");
  await page.getByRole("button", { name: "Create demo order" }).click();
  await page.getByLabel("Energy (kWh)", { exact: true }).fill("12.5");
  await page.getByLabel("Limit price (INR/kWh)", { exact: true }).fill("4.65");
  await page.getByRole("button", { name: "Save local draft" }).click();
  await expect(
    page.getByRole("heading", { name: "Demo draft saved" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back to marketplace" }).click();
  await expect(
    page.getByRole("heading", { name: "Your local drafts" }),
  ).toBeVisible();
  expect(writes).toEqual([]);
});
test("filters, scenarios and keyboard dialogs work", async ({ page }) => {
  await page.goto("/community");
  await page.getByRole("textbox", { name: "Search community" }).fill("Mehta");
  await expect(page.locator(".member-card")).toHaveCount(1);
  await page.locator(".member-card").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.goto("/trades");
  await page.getByRole("button", { name: "Rejected", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.goto("/grid");
  await page.getByRole("button", { name: "Missing data", exact: true }).click();
  await expect(
    page.getByText("Missing measurements prevent a safety decision."),
  ).toBeVisible();
});
test("API failures stay visible and real responses remain separate", async ({
  page,
}) => {
  await page.route("**/health", (r) =>
    r.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "DATABASE_UNAVAILABLE",
          message: "Database unavailable",
        },
      }),
    }),
  );
  await page.goto("/settings");
  await page.getByRole("button", { name: "Check API health" }).click();
  await expect(
    page.getByText("Connection failed: Database unavailable"),
  ).toBeVisible();
  await page.route("**/api/v1/sites/*", (r) =>
    r.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ name: "Real API site", generation_kw: null }),
    }),
  );
  await page
    .getByLabel("Resource UUID", { exact: true })
    .fill("10000000-0000-0000-0000-000000000001");
  await page.getByRole("button", { name: "Load record" }).click();
  await expect(page.locator(".json-result")).toContainText("Real API site");
  await expect(page.locator(".json-result")).toContainText("null");
});
test("settlement CSV can be downloaded", async ({ page }) => {
  await page.goto("/settlements");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export demo CSV" }).click();
  expect((await download).suggestedFilename()).toBe(
    "urjasetu-illustrative-settlements.csv",
  );
});
