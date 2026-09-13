import { test, expect, type Page } from "@playwright/test";

const headers = { "X-Requested-With": "UrjaSetu" };
export async function login(page: Page, account = "asha") {
  await page.goto("/");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`${account}@urjasetu.demo`);
  await page.getByLabel("Password", { exact: true }).fill("Sunshine2026!");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.locator(".ux-energy-hero")).toBeVisible({ timeout: 20000 });
}
async function post(page: Page, path: string, data: unknown) {
  const response = await page.request.post(`/api/v1${path}`, { headers, data });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(await page.evaluate(() => innerWidth));
}

test("five-second readings, range controls, all pages and logout", async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  const chart = page.getByRole("img", {
    name: "energy energy chart",
    exact: true,
  });
  await expect(chart).toBeVisible();
  const old = await chart.getAttribute("data-updated-at");
  const reading = await page.getByTestId("live-readings").innerText();
  await expect
    .poll(() => chart.getAttribute("data-updated-at"), { timeout: 11000 })
    .not.toBe(old);
  await expect
    .poll(() => page.getByTestId("live-readings").innerText(), {
      timeout: 11000,
    })
    .not.toBe(reading);
  const chartRange = page.getByRole("group", { name: "Chart range" });
  await chartRange
    .getByRole("button", { name: "Last hour", exact: true })
    .click();
  await expect(
    page.getByLabel("Reading interval", { exact: true }),
  ).toHaveValue("1m");
  await chartRange
    .getByRole("button", { name: "Last 24 hours", exact: true })
    .click();
  await expect(
    page.getByLabel("Reading interval", { exact: true }),
  ).toHaveValue("15m");
  await expect(chart).toBeVisible();
  await page
    .getByRole("button", { name: "View readings", exact: true })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(96);
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export readings", exact: true })
    .click();
  expect((await download).suggestedFilename()).toBe("household-readings.csv");
  for (const route of [
    "forecasts",
    "trades",
    "settlements",
    "audit",
    "community",
    "grid",
    "settings",
    "market",
  ]) {
    await page.goto(`/${route}`);
    await expect(page.locator(".ux-heading h1")).toBeVisible();
    await noOverflow(page);
    await expect(page.locator("main")).not.toContainText(
      /Synthetic Data|Mock Data|Simulation/i,
    );
  }
  await expect(page.getByRole("navigation")).not.toContainText("Overview");
  if (
    await page
      .getByRole("button", { name: "Open menu", exact: true })
      .isVisible()
  )
    await page.getByRole("button", { name: "Open menu", exact: true }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/workspace/dashboard")).status()).toBe(
    401,
  );
  expect(errors).toEqual([]);
});

test("Ravi accepts Asha's offer using his existing buy order; both receive the trade, settlement and chain receipt", async ({
  browser,
}, info) => {
  test.setTimeout(150000);
  const seller = await browser.newContext(info.project.use),
    buyer = await browser.newContext(info.project.use),
    operator = await browser.newContext(info.project.use);
  const a = await seller.newPage(),
    b = await buyer.newPage(),
    o = await operator.newPage();
  try {
    await login(a);
    await login(b, "ravi");
    await login(o, "operator");
    const data = await (
      await a.request.get("/api/v1/workspace/dashboard")
    ).json();
    const loads = new Map(
      data.forecasts
        .filter((p: { kind: string }) => p.kind === "load")
        .map((p: { interval_start: string; predicted_kwh: string }) => [
          p.interval_start,
          Number(p.predicted_kwh),
        ]),
    );
    const available = data.forecasts
      .filter(
        (p: { kind: string; predicted_kwh: string; interval_start: string }) =>
          p.kind === "solar" &&
          Number(p.predicted_kwh) - Number(loads.get(p.interval_start)) > 0.2,
      )
      .sort(
        (a: { predicted_kwh: string }, b: { predicted_kwh: string }) =>
          Number(b.predicted_kwh) - Number(a.predicted_kwh),
      );
    const slot = available[0].interval_start;
    await b.goto("/market");
    await b
      .getByRole("button", { name: "Create an order", exact: true })
      .click();
    await b.getByLabel("Delivery slot", { exact: false }).selectOption(slot);
    await b.getByLabel("Energy quantity", { exact: false }).fill("0.05");
    await b.getByLabel("Maximum price", { exact: false }).fill("8");
    await b.getByRole("button", { name: "Publish order", exact: true }).click();
    await expect(b.getByRole("dialog")).toHaveCount(0);
    await a.goto("/market");
    await a
      .getByRole("group", { name: "Marketplace view" })
      .getByRole("button", { name: "Sell energy", exact: true })
      .click();
    await a
      .getByRole("button", { name: "Create an order", exact: true })
      .click();
    await a.getByLabel("Delivery slot", { exact: false }).selectOption(slot);
    await a.getByLabel("Energy quantity", { exact: false }).fill("0.05");
    await a.getByLabel("Minimum price", { exact: false }).fill("4");
    const created = a.waitForResponse(
      (r) =>
        r.url().endsWith("/workspace/orders") &&
        r.request().method() === "POST",
    );
    await a.getByRole("button", { name: "Publish order", exact: true }).click();
    const offer = await (await created).json();
    const card = b.locator(`[data-offer-id="${offer.id}"]`);
    await expect(card).toBeVisible({ timeout: 12000 }); // Buyer never refreshes/navigates after Asha's write.
    await a.goto("/trades");
    await card.getByRole("button", { name: "Buy energy", exact: true }).click();
    await expect(b.getByLabel("Match with your order")).not.toHaveValue("");
    const accepted = b.waitForResponse((r) =>
      r.url().endsWith(`/orders/${offer.id}/accept`),
    );
    await b
      .getByRole("button", { name: "Confirm energy purchase", exact: true })
      .click();
    const response = await accepted;
    expect(response.status(), await response.text()).toBe(201);
    const trade = await response.json();
    await expect(a.locator(`[data-trade-id="${trade.id}"]`)).toContainText(
      "committed",
      { timeout: 12000 },
    );
    await b.goto("/trades");
    await expect(b.locator(`[data-trade-id="${trade.id}"]`)).toContainText(
      "committed",
    );
    // Test-only clock acceleration avoids waiting until tomorrow. Normal users
    // settle automatically at real 15-minute boundaries without this control.
    await post(o, "/workspace/control", { action: "deliver" });
    await expect(a.locator(`[data-trade-id="${trade.id}"]`)).toContainText(
      "settled",
      { timeout: 12000 },
    );
    await expect(b.locator(`[data-trade-id="${trade.id}"]`)).toContainText(
      "settled",
      { timeout: 12000 },
    );
    await b.goto("/settlements");
    await expect(b.locator("tbody tr").first()).toContainText("Asha Patel");
    const download = b.waitForEvent("download");
    await b.getByRole("button", { name: "Export to CSV", exact: true }).click();
    expect((await download).suggestedFilename()).toBe("energy-settlements.csv");
    await a.goto("/audit");
    const receipt = a.locator(`[data-trade-id="${trade.id}"]`);
    await expect(
      receipt.getByRole("button", {
        name: "Verify on blockchain",
        exact: true,
      }),
    ).toBeEnabled({ timeout: 25000 });
    await receipt
      .getByRole("button", { name: "Verify on blockchain", exact: true })
      .click();
    await expect(receipt.getByRole("status")).toContainText("Verified.");
  } finally {
    if (o.url() !== "about:blank")
      await post(o, "/workspace/control", { action: "live" });
    await seller.close();
    await buyer.close();
    await operator.close();
  }
});

test("registration personalizes 30-day history and adds a clickable household to another user's feeder", async ({
  browser,
}, info) => {
  test.setTimeout(90000);
  const resident = await browser.newContext(info.project.use),
    newcomer = await browser.newContext(info.project.use);
  const a = await resident.newPage(),
    n = await newcomer.newPage();
  const name = `Meera ${info.project.name}`;
  a.setDefaultTimeout(15000);
  n.setDefaultTimeout(15000);
  try {
    await login(a);
    await a.goto("/grid");
    await expect(
      a.getByRole("button", { name: "Inspect Asha Patel", exact: true }),
    ).toBeVisible();
    await n.goto("/");
    await n
      .getByRole("button", { name: "New here? Create an account", exact: true })
      .click();
    await n.getByLabel("Your name", { exact: true }).fill(name);
    await n
      .getByLabel("Email", { exact: true })
      .fill(`meera-${Date.now()}@example.test`);
    await n.getByLabel("Password", { exact: true }).fill("Household2026!");
    await n.getByLabel("Your energy setup").selectOption("prosumer");
    await n.getByLabel("Solar capacity", { exact: false }).fill("3");
    await n.getByRole("button", { name: "Continue", exact: true }).click();
    // Leave the wizard open across a refresh interval: background auth checks
    // must never reset a partially completed registration.
    await n.waitForTimeout(6000);
    await n.getByLabel("City", { exact: true }).selectOption("Surat");
    await n.getByLabel("People at home").fill("2");
    await n.getByLabel("Monthly consumption", { exact: false }).fill("180");
    await n.getByLabel("Air conditioners").fill("0");
    await n
      .getByRole("button", { name: "Join the community", exact: true })
      .click();
    await expect(n.locator(".ux-energy-hero")).toBeVisible({ timeout: 20000 });
    await expect(
      a.getByRole("button", { name: `Inspect ${name}`, exact: true }),
    ).toBeAttached({ timeout: 12000 });
    // New nodes can be outside a user's current pan/zoom; fit view is intentional.
    await a.getByRole("button", { name: "Fit View", exact: true }).click();
    await a
      .getByRole("button", { name: `Inspect ${name}`, exact: true })
      .click();
    await expect(a.getByRole("dialog")).toContainText("Surat");
    await expect(a.getByRole("dialog")).toContainText("3 kW rooftop");
    const stats = await a.locator(".ux-detail-stats").innerText();
    await a.getByRole("button", { name: "Close dialog", exact: true }).click();
    await a.goto("/community");
    await a.getByRole("button", { name: `View ${name}`, exact: true }).click();
    expect(await a.locator(".ux-detail-stats").innerText()).toBe(stats);
    await a
      .getByRole("dialog")
      .getByRole("button", { name: "Last month", exact: true })
      .click();
    const newData = await (
      await n.request.get("/api/v1/workspace/dashboard")
    ).json();
    expect(newData.periods.day.load_kwh).toBeGreaterThan(5.6);
    expect(newData.periods.day.load_kwh).toBeLessThan(6.4);
    expect(newData.daily.length).toBeGreaterThanOrEqual(30);
    await n.goto("/settings");
    await n
      .getByLabel("Share household energy totals with the community")
      .uncheck();
    await n
      .getByRole("button", { name: "Save household settings", exact: true })
      .click();
    await expect(a.getByRole("dialog")).toContainText(
      "keeps their energy statistics private",
      { timeout: 12000 },
    );
  } finally {
    await resident.close();
    await newcomer.close();
  }
});

test("profile photo persists and appears in community details", async ({
  page,
}) => {
  await login(page);
  await page.goto("/settings");
  const pixel = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a6uQAAAAASUVORK5CYII=",
    "base64",
  );
  await page.getByLabel("Your profile photo", { exact: true }).setInputFiles({
    name: "profile.png",
    mimeType: "image/png",
    buffer: pixel,
  });
  await page
    .getByRole("button", { name: "Save household settings", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("profile is updated");
  await page.reload();
  await expect(page.locator(".ux-profile-banner img")).toBeVisible();
  await page.goto("/community");
  await page
    .getByRole("button", { name: "View Asha Patel", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByAltText("Asha Patel's profile"),
  ).toBeVisible();
});

test("energy assistant answers from the account and navigates to the marketplace", async ({
  page,
}) => {
  await login(page, "ravi");
  await page
    .getByRole("button", { name: "Open energy assistant", exact: true })
    .click();
  await page.getByRole("button", { name: "My savings", exact: true }).click();
  await expect(page.locator(".ux-chat-message.assistant").last()).toContainText(
    "configured ₹7.00/kWh rate",
  );
  await page.getByLabel("Message Urja").fill("How do I buy energy?");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".ux-chat-message.assistant").last()).toContainText(
    "grid check pass",
  );
  await page.getByRole("link", { name: "Find energy", exact: true }).click();
  await expect(page).toHaveURL(/\/market$/);
  await expect(
    page.getByRole("dialog", { name: "Urja energy assistant" }),
  ).toHaveCount(0);
  await noOverflow(page);
});
