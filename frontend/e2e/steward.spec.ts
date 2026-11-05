import { expect, test } from "@playwright/test";

test("double-charge refund pauses for human approval, then completes", async ({ page }) => {
  await page.goto("/");
  await page.fill(".composer textarea",
    "I think I was charged twice for my subscription this month.");
  await page.click(".composer button[type=submit]");

  const panel = page.getByTestId("approval-panel");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel.getByTestId("approval-tool")).toContainText("issue_refund");
  await expect(panel).toContainText(/threshold/i);

  await panel.getByTestId("approve-btn").click();
  await expect(panel).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("messages")).toContainText(/refund/i, { timeout: 30_000 });

  await page.getByTestId("feedback-up").click();
  await expect(page.getByText(/feedback recorded/i)).toBeVisible();
});

test("low-confidence FAQ goes through draft review", async ({ page }) => {
  await page.goto("/");
  await page.fill(".composer textarea", "What is your refund policy window?");
  await page.click(".composer button[type=submit]");

  const panel = page.getByTestId("approval-panel");
  await expect(panel).toBeVisible({ timeout: 30_000 });
  await expect(panel).toContainText(/Reply needs review/i);
  await panel.getByTestId("approve-btn").click();
  await expect(panel).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId("messages")).toContainText(/refund/i, { timeout: 30_000 });
});