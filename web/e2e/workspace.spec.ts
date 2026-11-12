import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
test("upload, retrieve, inspect citations, export, and mobile layout", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Follow the evidence." }),
  ).toBeVisible();
  await page
    .locator("input[type=file]")
    .setInputFiles(
      fileURLToPath(
        new URL("../../examples/tracepaper-field-notes.pdf", import.meta.url),
      ),
    );
  await expect(page.getByText("1 indexed papers")).toBeVisible({
    timeout: 20000,
  });
  await page
    .getByLabel("Research question")
    .fill("How does citation coverage differ from citation correctness?");
  await page.getByLabel("Ask question", { exact: true }).click();
  await expect(page.getByText("02 / RETRIEVED EVIDENCE")).toBeVisible();
  await page.getByLabel("Inspect citation 1").first().click();
  await expect(page.locator(".source-passage")).toContainText(
    "Citation validity",
  );
  await expect(page.locator(".source-meta")).toContainText("PAGE 02");
  await page.screenshot({
    path: "/tmp/tracepaper-desktop.png",
    fullPage: true,
  });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export notes" }).click();
  expect((await download).suggestedFilename()).toBe("tracepaper-notes.md");
  await page
    .getByRole("button", { name: "Original page", exact: true })
    .click();
  await expect(page.getByTitle("Original PDF page")).toHaveAttribute(
    "src",
    /#page=2/,
  );
  await page.getByRole("button", { name: /All documents/ }).click();
  await expect(
    page.getByRole("link", { name: "tracepaper-field-notes.pdf" }),
  ).toBeVisible();
  await page
    .getByRole("checkbox", { name: "Select tracepaper-field-notes.pdf" })
    .check();
  await page.getByRole("button", { name: "Ask selected documents" }).click();
  await expect(page.getByText("1 selected papers")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "/tmp/tracepaper-mobile.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel("Open menu").click();
  await page.getByRole("button", { name: /Research insights/ }).click();
  await expect(
    page.getByRole("heading", { name: "Make the work measurable." }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("each visitor can add, replace, remove, and refresh a tab-only key", async ({
  page,
  browser,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Add API key", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByLabel("Gemini API key", { exact: true })
    .fill("visitor-one-test-key");
  await page.getByRole("button", { name: "Use key for this tab" }).click();
  await expect(page.locator(".system")).toContainText("Gemini · your key");
  expect(
    await page.evaluate(() =>
      JSON.stringify({
        local: { ...localStorage },
        session: { ...sessionStorage },
        cookies: document.cookie,
      }),
    ),
  ).not.toContain("visitor-one-test-key");
  // Credentials affect only this tab, not other visitors.
  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await otherPage.goto("/");
  await expect(
    otherPage.getByRole("button", { name: "Add API key", exact: true }),
  ).toBeVisible();
  await other.close();
  const keys: string[] = [];
  await page.route("**/api/ask", async (route) => {
    keys.push(route.request().headers()["x-provider-key"] || "");
    expect(JSON.stringify(route.request().postDataJSON())).not.toContain(
      "visitor-one-test-key",
    );
    await route.fulfill({
      json: {
        id: "mock",
        question: "citation correctness",
        claims: [],
        sources: [],
        mode: "generated",
        warning: null,
        insufficient: true,
        latency_ms: 20,
        estimated_cost_usd: null,
      },
    });
  });
  await page.getByLabel("Research question").fill("citation correctness");
  await page.getByLabel("Ask question", { exact: true }).click();
  await expect(page.getByText("02 / GROUNDED ANSWER")).toBeVisible();
  expect(keys).toEqual(["visitor-one-test-key"]);
  await page.locator(".system").click();
  await expect(page.getByLabel("Gemini API key", { exact: true })).toHaveValue(
    "",
  );
  await page
    .getByLabel("Gemini API key", { exact: true })
    .fill("visitor-one-replacement");
  await page.getByRole("button", { name: "Use key for this tab" }).click();
  await page.getByLabel("Ask question", { exact: true }).click();
  await expect.poll(() => keys.length).toBe(2);
  expect(keys[1]).toBe("visitor-one-replacement");
  await page.locator(".system").click();
  await page.getByRole("button", { name: "Remove key" }).click();
  await expect(page.locator(".system")).toHaveText("Add API key");
  await page.getByLabel("Ask question", { exact: true }).click();
  await expect.poll(() => keys.length).toBe(3);
  expect(keys[2]).toBe("");
  await page.locator(".system").click();
  await page
    .getByLabel("Gemini API key", { exact: true })
    .fill("forgotten-on-reload");
  await page.getByRole("button", { name: "Use key for this tab" }).click();
  await page.reload();
  await expect(page.locator(".system")).toHaveText("Add API key");
  // Native dialog supports keyboard dismissal and responsive layout.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator(".system").click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({
    path: "/tmp/tracepaper-key-settings.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
});

test("DOCX sections, unsupported uploads, failed parsing, search, and deletion", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .locator("input[type=file]")
    .setInputFiles(
      fileURLToPath(
        new URL("../../examples/tracepaper-field-notes.docx", import.meta.url),
      ),
    );
  await page.getByRole("button", { name: /All documents/ }).click();
  const wordRow = page
    .locator(".document-row")
    .filter({ hasText: "tracepaper-field-notes.docx" });
  await expect(wordRow.locator(".badge")).toHaveText("ready", {
    timeout: 20000,
  });
  await wordRow.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Ask selected documents" }).click();
  await page.getByLabel("Research question").fill("citation correctness");
  await page.getByLabel("Ask question", { exact: true }).click();
  await expect(page.locator(".source-meta")).toContainText("SECTION");
  await expect(page.locator(".source-heading")).toContainText(".docx");
  await expect(
    page.getByRole("button", { name: "Original page", exact: true }),
  ).toHaveCount(0);
  await page.locator("input[type=file]").setInputFiles({
    name: "unsupported.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("Not a supported document"),
  });
  await expect(page.getByRole("alert")).toContainText(
    "Choose a PDF or DOCX file.",
  );
  await page.getByLabel("Dismiss error").click();
  await page.locator("input[type=file]").setInputFiles({
    name: "broken.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("Not a valid PDF"),
  });
  await page.getByRole("button", { name: /All documents/ }).click();
  const broken = page
    .locator(".document-row")
    .filter({ hasText: "broken.pdf" });
  await expect(broken.locator(".badge")).toHaveText("failed", {
    timeout: 20000,
  });
  await broken.getByRole("button", { name: "Delete broken.pdf" }).click();
  await page.getByRole("button", { name: "Keep document" }).click();
  await expect(broken).toBeVisible();
  await broken.getByRole("button", { name: "Delete broken.pdf" }).click();
  await page
    .getByRole("button", { name: "Remove document", exact: true })
    .click();
  await expect(broken).toHaveCount(0);
  await page
    .getByLabel("Search documents")
    .fill("there-is-no-document-by-this-name");
  await expect(
    page.getByRole("heading", { name: "No matching titles." }),
  ).toBeVisible();
  await page.getByLabel("Search documents").fill("");
  await wordRow
    .getByRole("button", { name: "Delete tracepaper-field-notes.docx" })
    .click();
  await page
    .getByRole("button", { name: "Remove document", exact: true })
    .click();
  await expect(wordRow).toHaveCount(0);
});
