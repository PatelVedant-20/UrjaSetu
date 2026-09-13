import { test, expect } from "@playwright/test";
test("capture redesigned My Energy on desktop and mobile", async ({
  page,
}, info) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("asha@urjasetu.demo");
  await page.getByLabel("Password", { exact: true }).fill("Sunshine2026!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.locator(".uw-chart .recharts-area-curve").first(),
  ).toBeVisible({ timeout: 15000 });
  expect(
    (await page
      .locator('.uw-chart svg[role="application"]')
      .first()
      .boundingBox())!.width,
  ).toBeGreaterThan(200);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: `/tmp/urjasetu-redesign-${info.project.name}.png`,
    fullPage: true,
    animations: "disabled",
  });
});
