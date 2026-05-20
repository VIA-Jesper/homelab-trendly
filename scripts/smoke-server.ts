/**
 * Server smoke test
 * Run with: npm run smoke:server
 *
 * Starts the Trendly server as a subprocess, runs HTTP checks against it,
 * then kills it. Requires data/products.json to exist (run `npm run seed` first).
 */

import { spawn, type ChildProcess } from "child_process";
import axios from "axios";

const PORT = 3000;
const BASE = `http://localhost:${PORT}`;
const GREEN = "\x1b[32m✓\x1b[0m";
const RED   = "\x1b[31m✗\x1b[0m";
const CYAN  = "\x1b[36m";
const RESET = "\x1b[0m";

let passed = 0;
let failed = 0;

function check(label: string, condition: boolean, detail?: string): void {
  if (condition) { console.log(`  ${GREEN} ${label}`); passed++; }
  else { console.log(`  ${RED} ${label}${detail ? ` — ${detail}` : ""}`); failed++; }
}

async function waitForServer(timeoutMs = 15_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await axios.get(`${BASE}/mcp-info`, { timeout: 1000 });
      return;
    } catch {
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  throw new Error("Server did not start within timeout");
}

async function runChecks(): Promise<void> {
  // ── GET /mcp-info ──────────────────────────────────────────────────────────
  console.log(`\n${CYAN}▶ GET /mcp-info${RESET}`);
  const mcpInfo = await axios.get<{
    mcpPort: number; transport: string; endpoint: string; tools: string[];
  }>(`${BASE}/mcp-info`);
  check("HTTP 200", mcpInfo.status === 200);
  check("mcpPort is 3001", mcpInfo.data.mcpPort === 3001);
  check("transport is streamable-http", mcpInfo.data.transport === "streamable-http");
  check("tools includes get_brief", mcpInfo.data.tools.includes("get_brief"));
  check("tools includes publish_article", mcpInfo.data.tools.includes("publish_article"));

  // ── GET /openapi.json ──────────────────────────────────────────────────────
  console.log(`\n${CYAN}▶ GET /openapi.json${RESET}`);
  const spec = await axios.get<{ openapi: string; info: { title: string } }>(`${BASE}/openapi.json`);
  check("HTTP 200", spec.status === 200);
  check("openapi version 3.1.0", spec.data.openapi === "3.1.0");
  check("title is Trendly API", spec.data.info.title === "Trendly API");

  // ── POST /generate — create a brief ───────────────────────────────────────
  console.log(`\n${CYAN}▶ POST /generate${RESET}`);
  let jobId: string | undefined;
  try {
    const gen = await axios.post<{ job_id: string; brief: { brief_id: string; products: unknown[] } }>(
      `${BASE}/generate`,
      { category: "laptops", site: "techblog" }
    );
    check("HTTP 202", gen.status === 202);
    check("job_id is a UUID", /^[0-9a-f-]{36}$/.test(gen.data.job_id));
    check("brief has products array", Array.isArray(gen.data.brief.products));
    check("brief has brief_id", typeof gen.data.brief.brief_id === "string");
    jobId = gen.data.job_id;
    console.log(`  job_id: ${jobId}`);
  } catch (err: unknown) {
    const msg = axios.isAxiosError(err) ? `${err.response?.status} ${JSON.stringify(err.response?.data)}` : String(err);
    check("POST /generate succeeded", false, msg);
  }

  // ── GET /generate/:id/brief ────────────────────────────────────────────────
  if (jobId) {
    console.log(`\n${CYAN}▶ GET /generate/${jobId}/brief${RESET}`);
    const brief = await axios.get<{ category: string }>(`${BASE}/generate/${jobId}/brief`);
    check("HTTP 200", brief.status === 200);
    check("brief.category is a string", typeof brief.data.category === "string");
  }

  // ── GET /generate/:id/status ───────────────────────────────────────────────
  if (jobId) {
    console.log(`\n${CYAN}▶ GET /generate/${jobId}/status${RESET}`);
    const status = await axios.get<{ status: string }>(`${BASE}/generate/${jobId}/status`);
    check("HTTP 200", status.status === 200);
    check("status is briefed", status.data.status === "briefed");
  }
}

async function main(): Promise<void> {
  console.log("Server smoke test");
  console.log("=".repeat(50));

  let server: ChildProcess | undefined;
  try {
    console.log("Starting server…");
    server = spawn("npx", ["tsx", "src/server.ts"], {
      env: { ...process.env, PORT: String(PORT) },
      stdio: ["ignore", "pipe", "pipe"],
      shell: true,
    });

    server.stderr?.on("data", (d: Buffer) => {
      const line = d.toString();
      if (line.includes("Error") || line.includes("error")) process.stderr.write(line);
    });

    await waitForServer();
    console.log(`Server ready at ${BASE}\n`);

    await runChecks();
  } finally {
    if (server) { server.kill(); console.log("\nServer stopped."); }
  }

  console.log("\n" + "=".repeat(50));
  if (failed === 0) { console.log(`${GREEN} All ${passed} checks passed`); }
  else { console.log(`${RED} ${failed}/${passed + failed} checks failed`); process.exit(1); }
}

main().catch((err) => { console.error("Fatal:", err); process.exit(1); });
