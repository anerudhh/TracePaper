import { defineConfig } from "@playwright/test";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const testData = mkdtempSync(join(tmpdir(), "tracepaper-browser-"));
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8123",
    launchOptions: {
      executablePath:
        process.env.CHROMIUM_PATH ||
        (existsSync("/usr/bin/chromium") ? "/usr/bin/chromium" : undefined),
      args: ["--no-sandbox"],
    },
  },
  webServer: {
    command:
      "../.venv/bin/python -m uvicorn backend.main:app --app-dir .. --host 127.0.0.1 --port 8123",
    url: "http://127.0.0.1:8123/api/health",
    reuseExistingServer: false,
    env: {
      TRACEPAPER_DATA: testData,
      TRACEPAPER_PASSWORD: "",
      TRACEPAPER_OCR: "0",
    },
  },
});
