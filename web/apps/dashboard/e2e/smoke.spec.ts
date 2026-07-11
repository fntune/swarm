import { expect, test } from "@playwright/test";

/**
 * Worker-free operator smoke: exercises auth, proxying, submission, the run
 * workspace, and cancellation against a live api + postgres + redis stack.
 * No runtime credentials are needed — the run stays queued until cancelled.
 */

const API_TOKEN = process.env.E2E_API_TOKEN ?? "dev-token";

test("rejects an invalid API token", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("API token").fill("definitely-wrong");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Invalid API token")).toBeVisible();
});

test("allows re-login after a stored token becomes invalid", async ({ context, page, baseURL }) => {
  if (!baseURL) throw new Error("Playwright baseURL is required");
  await context.addCookies([
    {
      name: "spawnd_token",
      value: "rotated-token",
      url: baseURL,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.goto("/login");

  await expect(page.getByText("Operator login", { exact: true })).toBeVisible();
  await expect(page.getByLabel("API token")).toBeVisible();
  expect((await context.cookies()).some((cookie) => cookie.name === "spawnd_token")).toBe(false);
});

test("operator journey: login → submit → watch → cancel", async ({ page }) => {
  const runId = `e2e-smoke-${Date.now()}`;

  await test.step("login with the deployed token", async () => {
    await page.goto("/login");
    await page.getByLabel("API token").fill(API_TOKEN);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/");
  });

  await test.step("overview renders fleet stats", async () => {
    await expect(page.getByText("active runs")).toBeVisible();
    await expect(page.getByText("queue depth")).toBeVisible();
  });

  await test.step("submit a minimal plan from the composer", async () => {
    await page.goto("/new");
    const editor = page.locator(".cm-content");
    await editor.click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.insertText(
      `name: e2e-smoke\nagents:\n  - name: solo\n    prompt: E2E smoke placeholder task\n`,
    );
    await page.getByLabel("run_id (optional)").fill(runId);
    await page.getByRole("button", { name: "Submit run" }).click();
    await page.waitForURL(`**/runs/${runId}`);
  });

  await test.step("run workspace shows the queued DAG", async () => {
    await expect(page.getByRole("heading", { name: runId })).toBeVisible();
    await expect(page.locator(".react-flow")).toBeVisible();
    await expect(page.locator(".react-flow").getByText("solo")).toBeVisible();
    await expect(page.getByText("queued").first()).toBeVisible();
  });

  await test.step("cancel the run and observe the terminal status", async () => {
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await page.getByRole("button", { name: "Confirm cancel" }).click();
    await expect(page.getByText("cancelled").first()).toBeVisible({ timeout: 15_000 });
  });
});
