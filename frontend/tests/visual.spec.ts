import { test } from "@playwright/test";
test("capture overview for visual review", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.locator(".chart svg").first().waitFor();
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: `/tmp/urjasetu-${testInfo.project.name}.png`,
    fullPage: true,
    animations: "disabled",
  });
});
