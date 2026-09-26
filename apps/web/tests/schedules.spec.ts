import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
// Actual components rendered with test-only data; no test hooks in the public app.
const markup = JSON.parse(
  readFileSync(".test-fixtures/schedules.json", "utf8"),
) as Record<string, string>;
for (const [name, html] of Object.entries(markup))
  test(`construction UI: ${name}`, async ({ page }) => {
    await page.goto("/");
    await page.locator("body").evaluate((body, content) => {
      body.innerHTML = content;
    }, html);
    const timeline = page.locator(".timeline");
    await expect(page.locator("body")).not.toContainText("NaN");
    await expect(page.locator("body")).not.toContainText("Invalid Date");
    await expect(page.locator("body")).not.toContainText("999");
    const valid = ["complete", "touching", "disjoint"].includes(name);
    await expect(timeline.locator(".timeline-bar")).toHaveCount(
      valid
        ? 2
        : ["empty", "missing", "no-valid-windows"].includes(name)
          ? 0
          : 1,
    );
    await expect(timeline.locator(".overlap-highlight")).toHaveCount(
      name === "complete" ? 2 : 0,
    );
    if (name === "complete")
      await expect(timeline).toContainText("5 shared days");
    if (name === "start-only") {
      await expect(page.locator(".details")).toContainText(
        "Known construction start: Jan 6, 2027",
      );
      await expect(timeline).toContainText("Construction end: Not provided");
    }
    if (name === "end-only") {
      await expect(page.locator(".details")).toContainText(
        "Known construction end: Jan 16, 2027",
      );
      await expect(timeline).toContainText("Construction start: Not provided");
    }
    if (["neither", "milestone-only"].includes(name))
      await expect(timeline).toContainText("Construction dates not provided");
    if (["reversed", "equal", "impossible", "malformed"].includes(name)) {
      await expect(page.locator(".details")).toContainText(
        "Invalid construction schedule",
      );
      await expect(page.locator(".opportunity")).toContainText(
        "Invalid schedule — review required",
      );
    }
    if (name === "impossible")
      await expect(page.locator(".details")).toContainText("2027-02-30");
    if (name === "malformed")
      await expect(page.locator(".details")).toContainText(
        "Invalid date — review required",
      );
    if (name === "missing")
      await expect(timeline).toContainText("Project data unavailable");
    if (name === "empty") {
      await expect(timeline).toContainText(
        "Select a pair to compare construction windows.",
      );
      await expect(timeline.locator(".mini-badge")).toHaveCount(0);
    }
    if (["empty", "missing", "no-valid-windows"].includes(name))
      await expect(timeline.locator(".timeline-scale")).toHaveCount(0);
    for (const bar of await timeline.locator(".timeline-bar").all()) {
      const style = await bar.getAttribute("style");
      expect(style).not.toMatch(/NaN|Infinity|(?:width|left):\s*-/);
    }
  });
