import { test, expect } from "@playwright/test";
test("live basemap and unknown schedule selection", async ({ page }) => {
  const mapWarnings: string[] = [];
  page.on("console", (message) => {
    if (message.text().includes("Map content error:"))
      mapWarnings.push(message.text());
  });
  const tile = page.waitForResponse(
    (response) =>
      response.url().startsWith("https://tile.openstreetmap.org/") &&
      response.ok(),
  );
  await page.goto("/");
  await tile;
  await expect(page.locator(".map-marker")).toHaveCount(7);
  await page
    .locator(".opportunity")
    .filter({ hasText: "SCHEDULE NEEDED" })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Schedule to be confirmed" }),
  ).toBeVisible();
  await expect(page.locator(".unknown-timing")).toBeVisible();
  await expect(page.locator(".map-marker.active")).toHaveCount(2);
  await expect(page.locator(".map-error")).toHaveCount(0);
  expect(mapWarnings).toEqual([]);
  await page.screenshot({
    path: "test-results/dashboard-live-map.png",
    fullPage: true,
  });
});
test("selection, filters, evidence, responsive layout, and map failure", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.abort(),
  );
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Find the overlap." }),
  ).toBeVisible();
  const cards = page.locator(".opportunity");
  await cards.nth(1).click();
  await expect(cards.nth(1)).toHaveAttribute("aria-pressed", "true");
  const projectName = await cards
    .nth(1)
    .locator(".card-project strong")
    .first()
    .innerText();
  await expect(
    page.locator(".details").getByRole("heading", { name: projectName }),
  ).toBeVisible();
  await page.locator(".evidence summary").first().click();
  await expect(page.locator(".evidence details").first()).toHaveAttribute(
    "open",
    "",
  );
  await page
    .getByRole("slider", { name: "Maximum distance in miles" })
    .fill("0.1");
  await expect(page.getByText("No opportunities in this range")).toBeVisible();
  await expect(
    page.locator(".details").getByRole("heading", { name: "Pair details" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Reset filters", exact: true })
    .first()
    .click();
  await expect(cards.first()).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".map-error")).toBeVisible({ timeout: 20000 });
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Find the overlap." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
