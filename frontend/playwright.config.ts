import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: "http://localhost:5173" },
  webServer: [
    {
      command: "bash -c 'cd ../backend && python -m app.db.ensure && uvicorn app.main:app --port 8000'",
      url: "http://localhost:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        AGENT_FAKE_MODEL: "true",
        AGENT_DATABASE_URL: "postgresql://steward:steward@localhost:5432/billing",
        AGENT_CHECKPOINT_DB_URL: "postgresql://steward:steward@localhost:5432/agent_checkpoints",
      },
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});