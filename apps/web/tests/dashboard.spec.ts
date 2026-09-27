import { test, expect, type Page } from "@playwright/test";

const project = (
  id: string,
  utility: string,
  x: number,
  milestone = false,
) => ({
  project_id: id,
  utility_id: utility,
  project_name: `Project ${id}`,
  project_type: "substation",
  status: "planned",
  location_text: "Savannah, Georgia",
  geometry: { type: "Point", coordinates: [x, 32] },
  geometry_origin: "CENTER_POINT",
  geometry_quality: "APPROXIMATE",
  validation_state: "NEEDS_REVIEW",
  schedule: milestone
    ? { type: "IN_SERVICE_GAP", in_service_date: "2027-06-01" }
    : {
        type: "CONSTRUCTION_WINDOW",
        start: { earliest: "2027-01-01", latest: "2027-01-01" },
        end_exclusive: { earliest: "2028-01-01", latest: "2028-01-01" },
      },
  evidence: [
    {
      source_id: "filing-001",
      source_name: "Test utility filing",
      page_or_row: "Page 4",
    },
  ],
});
const projects = [
  project("A", "UTILITY_A", -81.05),
  project("B", "UTILITY_B", -81.04),
  project("C", "UTILITY_B", -81.03, true),
];
const matches = [
  {
    pair_id: "pair/A+B",
    projects: [projects[0], projects[1]],
    distance: { meters: 8000 },
    tier: "HIGH",
  },
  {
    pair_id: "pair/A+C",
    projects: [projects[0], projects[2]],
    distance: { meters: 1000 },
    tier: "POSSIBLE",
  },
];
async function mockApi(page: Page, empty = false) {
  await page.route(
    "https://gridlock-api-production.up.railway.app/api/v1/**",
    async (route) => {
      const path = new URL(route.request().url()).pathname;
      let body: unknown;
      if (path.endsWith("/projects/geojson"))
        body = {
          type: "FeatureCollection",
          features: empty
            ? []
            : projects.map((p) => ({
                type: "Feature",
                properties: { project_id: p.project_id },
                geometry: p.geometry,
              })),
        };
      else if (path.endsWith("/projects")) body = empty ? [] : projects;
      else if (path.endsWith("/opportunities")) body = empty ? [] : matches;
      else
        body = matches.find((m) =>
          path.endsWith(encodeURIComponent(m.pair_id)),
        );
      await route.fulfill({ json: body });
    },
  );
}

test("API ranking, selection, timeline, evidence and responsive layout", async ({
  page,
}) => {
  await mockApi(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator(".opportunity")).toHaveCount(2);
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("link", { name: "Skip to coordination workspace" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#workspace-main")).toBeFocused();
  await expect(page.locator(".scene-viewport canvas")).toBeVisible();
  // API order deliberately has the farther match first.
  await expect(page.locator(".opportunity").first()).toContainText("HIGH");
  await expect(page.locator(".opportunity").first()).toContainText("4.97 mi");
  await page.getByLabel("Selected date", { exact: true }).fill("2027-05-01");
  await expect(page.locator(".relationship-summary")).toContainText(
    "COLLISION / SYNERGY ALERT",
  );
  const detailRequest = page.waitForRequest((r) =>
    r.url().endsWith("/opportunities/pair%2FA%2BC"),
  );
  await page.locator(".opportunity").nth(1).click();
  await detailRequest;
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page
    .getByRole("button", { name: /Open Co-Procurement Dossier/ })
    .click();
  await expect(page.locator(".dossier")).toContainText("Test utility filing");
  await expect(page.locator(".dossier")).toContainText(
    "Jun 1, 2027 (not a construction window)",
  );
  await expect(page.locator(".dossier")).toContainText("NEEDS_REVIEW");
  await expect(page.locator(".dossier")).toHaveCSS("opacity", "1");
  await expect(page.locator(".timeline")).toContainText("In-service milestone");
  await expect(page.locator(".map-distance")).toContainText("0.62 mi");
  await page
    .getByRole("slider", { name: "Maximum distance in miles" })
    .fill("0.1");
  await expect(page.getByText("No opportunities in this range")).toBeVisible();
  await page
    .getByRole("button", { name: "Reset filters", exact: true })
    .click();
  await expect(page.locator(".opportunity")).toHaveCount(2);
  await page.getByLabel("Utility A", { exact: true }).selectOption("UTILITY_B");
  await expect(page.getByLabel("Utility B", { exact: true })).toHaveValue(
    "UTILITY_A",
  );
  await page.getByRole("button", { name: "Reset View" }).click();
  for (const width of [1440, 900, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/live-${width}.png`,
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
});

test("empty API shows an honest empty state with no demo fallback", async ({
  page,
}) => {
  await mockApi(page, true);
  await page.goto("/");
  await expect(page.getByText("No projects available yet")).toBeVisible();
  await expect(
    page.getByText("No opportunities returned by the API"),
  ).toBeVisible();
  await expect(page.locator(".opportunity")).toHaveCount(0);
  await expect(
    page.getByText("No mapped project geometry available."),
  ).toBeVisible();
});

test("failed initial request can be retried", async ({ page }) => {
  await mockApi(page);
  let fail = true;
  await page.route("**/api/v1/projects", async (route) => {
    if (fail) await route.fulfill({ status: 503, body: "Unavailable" });
    else await route.fulfill({ json: projects });
  });
  await page.goto("/");
  await expect(page.getByRole("alert").filter({hasText:"Could not load project data"})).toContainText("503");
  fail = false;
  await page.getByRole("button", { name: "Retry connection" }).click();
  await expect(page.locator(".opportunity")).toHaveCount(2);
});

test("detail error and retry do not break the list or map", async ({
  page,
}) => {
  await mockApi(page);
  let fail = true;
  await page.route("**/api/v1/opportunities/*", async (route) => {
    if (fail) await route.fulfill({ status: 502, body: "Unavailable" });
    else await route.fulfill({ json: matches[0] });
  });
  await page.goto("/");
  await page
    .getByRole("button", { name: /Open Co-Procurement Dossier/ })
    .click();
  await expect(page.getByRole("alert").filter({hasText:"Could not load match details"})).toContainText("502");
  fail = false;
  await page.getByRole("button", { name: "Retry details" }).click();
  await expect(page.locator(".dossier")).toBeVisible();
  await expect(page.locator(".opportunity")).toHaveCount(2);
});

test("late detail responses cannot replace the selected pair", async ({
  page,
}) => {
  await mockApi(page);
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/opportunities/*", async (route) => {
    const first = route.request().url().endsWith("pair%2FA%2BB");
    if (first) await delayed;
    await route
      .fulfill({ json: first ? matches[0] : matches[1] })
      .catch(() => {});
  });
  await page.goto("/");
  await page.locator(".opportunity").nth(1).click();
  await page
    .getByRole("button", { name: /Open Co-Procurement Dossier/ })
    .click();
  await expect(page.locator(".dossier")).toContainText("Project C");
  release();
  await expect(page.locator(".dossier")).not.toContainText("Project B");
});
