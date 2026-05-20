import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const sampleCsv = "id,amount,state\n1,100,AL\n2,1020,AX\n3,105,AL\n";

const profilePayload = {
  issues: [
    {
      column: "state",
      issue_type: "fd_violation",
      severity: "unsafe",
      row_indices: [1],
      count: 1,
    },
    {
      column: "amount",
      issue_type: "decimal_shift",
      severity: "review",
      row_indices: [2],
      count: 1,
    },
  ],
  meta: {
    rows: 3,
    columns: 3,
    column_names: ["id", "amount", "state"],
    total_issues: 2,
    advanced_requested: false,
    api_version: "0.1.0",
    contract_version: "repair_contract_v2",
  },
};

const repairPayload = {
  fixes: [
    {
      row: 2,
      column: "amount",
      old_value: "1020",
      new_value: "102",
      detector_id: "decimal_shift",
      reason: "Tenfold outlier relative to neighboring rows.",
      confidence: 0.91,
      provenance: "heuristic",
    },
  ],
  txn_journal: {
    txn_id: "txn-demo",
    created_at: "2026-05-20T12:00:00Z",
    source_name: "hospital_10rows.csv",
    source_sha256: "a".repeat(64),
    fixes_count: 1,
    applied: false,
    events: [{ event_type: "created" }],
    note: "Playground is stateless.",
  },
  meta: {
    api_version: "0.1.0",
    contract_version: "repair_contract_v2",
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/health", async (route) => {
    await route.fulfill({
      json: {
        status: "ok",
        advanced_available: false,
        max_upload_bytes: 1_048_576,
      },
    });
  });
  await page.route("**/api/samples/hospital_10rows", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/csv",
      body: sampleCsv,
      headers: { "content-disposition": 'attachment; filename="hospital_10rows.csv"' },
    });
  });
  await page.route("**/api/samples/flights_10rows", async (route) => {
    await route.fulfill({ status: 200, contentType: "text/csv", body: sampleCsv });
  });
  await page.route("**/api/samples/beers_10rows", async (route) => {
    await route.fulfill({ status: 200, contentType: "text/csv", body: sampleCsv });
  });
  await page.route("**/api/profile**", async (route) => {
    await route.fulfill({ json: profilePayload });
  });
  await page.route("**/api/repair**", async (route) => {
    await route.fulfill({ json: repairPayload });
  });
});

test("sample path profiles, repairs, exports evidence, and passes automated accessibility", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-write"]);
  await page.goto("/");

  await page.getByRole("button", { name: /Hospital/ }).click();
  await expect(page.getByRole("heading", { name: "Current CSV" })).toBeVisible();
  await expect(page.getByText("1020")).toBeVisible();

  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByText("fd_violation")).toBeVisible();

  await page.getByRole("button", { name: /Repair dry run/ }).click();
  await expect(page.getByText("Tenfold outlier")).toBeVisible();

  const repairTab = page.getByRole("tab", { name: "Repair" });
  await repairTab.focus();
  await repairTab.press("ArrowRight");
  await expect(page.getByText("txn-demo", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Copy" }).click();
  await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  await expect((await download).suggestedFilename()).toContain("dataforge-dry-run");

  const scan = await new AxeBuilder({ page }).analyze();
  expect(scan.violations).toEqual([]);
});

test("uploaded CSV path validates and profiles without samples", async ({ page }) => {
  await page.goto("/");

  await page
    .locator("#csv-upload")
    .setInputFiles({ name: "upload.csv", mimeType: "text/csv", buffer: Buffer.from(sampleCsv) });

  await expect(page.getByText("upload.csv")).toBeVisible();
  await page.getByRole("button", { name: "Profile" }).click();
  await expect(page.getByText("decimal_shift")).toBeVisible();
});

test("client rejects files above the health capability limit", async ({ page }) => {
  await page.goto("/");

  await page.locator("#csv-upload").setInputFiles({
    name: "big.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(`id\n${"x".repeat(1_048_577)}`),
  });

  await expect(page.getByRole("alert")).toContainText("larger than the hosted playground limit");
});

test("tabs support arrow-key navigation", async ({ page }) => {
  await page.goto("/");

  const profileTab = page.getByRole("tab", { name: "Profile" });
  await profileTab.focus();
  await profileTab.press("ArrowRight");

  await expect(page.getByRole("tab", { name: "Repair" })).toHaveAttribute("aria-selected", "true");
});
