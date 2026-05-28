import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { createServer } from "http";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { v4 as uuidv4 } from "uuid";
import { z } from "zod";
import { createRun, getRun, setBrief } from "../services/article-store.js";
import { generateBriefAsync } from "../services/brief-generator.js";
import { publish } from "../services/publish-service.js";
import { validateArticleV2 } from "../services/validator.js";
import { discoverBestCategory } from "../services/category-discoverer.js";
import { AnchoredPlacementSchema, SeoPayloadSchema } from "../types/index.js";
import type { ContentBrief, AnchoredPlacement } from "../types/index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROMPTS_DIR = resolve(__dirname, "../../prompts/agents");

function safeRead(filePath: string): string {
  try { return readFileSync(filePath, "utf-8"); }
  catch { return ""; }
}

function loadWritingInstructions(articleType: string | undefined): string {
  const universal = safeRead(resolve(PROMPTS_DIR, "generator.md"));
  const typeModule = articleType
    ? safeRead(resolve(PROMPTS_DIR, `generator-types/${articleType}.md`))
    : "";
  return typeModule ? `${universal}\n\n---\n\n${typeModule}` : universal;
}

const MCP_PORT = Number(process.env["MCP_PORT"] ?? 3001);

export async function startMcpServer(): Promise<void> {
  const server = new McpServer({
    name: "trendly",
    version: "2.0.0",
  });

  // ─── Tool: get_brief ─────────────────────────────────────────────────────
  server.tool(
    "get_brief",
    "Generate a content brief for an affiliate article. Returns product data, writing rules, and a job_id to use with publish_article.",
    {
      site: z.string().describe("Site key, e.g. 'techblog'"),
      category: z.string().optional().describe("PriceRunner category name (omit to auto-select)"),
      productUrl: z.string().optional().describe("Specific PriceRunner product URL"),
    },
    async ({ site, category, productUrl }) => {
      // Dynamic discovery: when the agent omits category, find the best one automatically
      let resolvedCategory = category;
      let resolvedCategoryId: string | undefined;

      if (!category && !productUrl) {
        try {
          const discovered = await discoverBestCategory(site);
          if (discovered) {
            resolvedCategory = discovered.categorySlug;
            resolvedCategoryId = discovered.categoryId;
            console.log(`[mcp/get_brief] Discovered category: "${discovered.categoryName}" (${discovered.categoryId})`);
          }
        } catch (err) {
          console.warn("[mcp/get_brief] Category discovery failed, falling back to traversal:", err);
        }
      }

      const result = await generateBriefAsync(resolvedCategory, productUrl, site, resolvedCategoryId);

      if ("error" in result) {
        return {
          content: [{ type: "text" as const, text: JSON.stringify(result) }],
          isError: true,
        };
      }

      const runId = createRun(site, "mcp");
      setBrief(runId, result);

      const writingInstructions = loadWritingInstructions(result.articleType);
      return {
        content: [{
          type: "text" as const,
          text: JSON.stringify({ run_id: runId, brief: result, writingInstructions }),
        }],
      };
    }
  );

  // ─── Tool: publish_article ───────────────────────────────────────────────
  server.tool(
    "publish_article",
    "Publish a Markdown article to WordPress. Injects widgets/images at specified placements, converts Markdown to HTML, adds affiliate links, and posts to WP.",
    {
      run_id: z.number().int().describe("The run_id returned by get_brief"),
      article: z.string().describe("Article content in Markdown"),
      site: z.string().describe("Site key, e.g. 'techblog'"),
      status: z.enum(["publish", "draft"]).default("draft").describe("Whether to publish or save as draft"),
      placements: z.array(AnchoredPlacementSchema).default([]).describe("Where to inject images/widgets"),
      seo: SeoPayloadSchema.optional().describe("SEO metadata for RankMath"),
    },
    async ({ run_id, article, site, status, placements, seo }) => {
      const run = getRun(run_id);
      const brief: ContentBrief | null = run?.brief_json ? JSON.parse(run.brief_json) : null;
      if (!brief) {
        return {
          content: [{ type: "text" as const, text: JSON.stringify({ error: "run_not_found", run_id }) }],
          isError: true,
        };
      }

      try {
        const result = await publish({
          runId: run_id,
          article,
          brief,
          siteKey: site,
          placements: placements as AnchoredPlacement[],
          seo,
          status,
        });
        if (result.status === "rejected") {
          return {
            content: [{ type: "text" as const, text: JSON.stringify(result) }],
            isError: true,
          };
        }
        return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        return {
          content: [{ type: "text" as const, text: JSON.stringify({ error: msg }) }],
          isError: true,
        };
      }
    }
  );

  // ─── Tool: validate_article ──────────────────────────────────────────────
  server.tool(
    "validate_article",
    "Validate a Markdown article against its brief before publishing. Returns pass/fail, word count, scores, and specific issues to fix.",
    {
      run_id: z.number().int().describe("run_id from get_brief"),
      article: z.string().describe("Article content in Markdown"),
      placements: z.array(AnchoredPlacementSchema).default([]).describe("Planned widget/image placements"),
    },
    async ({ run_id, article, placements }) => {
      const run = getRun(run_id);
      const brief: ContentBrief | null = run?.brief_json ? JSON.parse(run.brief_json) : null;
      if (!run || !brief) {
        return {
          content: [{ type: "text" as const, text: JSON.stringify({ error: "run_not_found", run_id }) }],
          isError: true,
        };
      }
      const result = validateArticleV2(article, brief, placements as AnchoredPlacement[], run.site_key);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }
  );

  // ─── HTTP server for Streamable HTTP transport ────────────────────────────
  const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: uuidv4 });
  await server.connect(transport);

  const httpServer = createServer((req, res) => {
    if (req.method === "POST" && req.url === "/mcp") {
      transport.handleRequest(req, res);
    } else {
      res.writeHead(404);
      res.end("Not found");
    }
  });

  await new Promise<void>((resolve) => httpServer.listen(MCP_PORT, "0.0.0.0", resolve));
  console.log(`🤖 MCP server    http://localhost:${MCP_PORT}/mcp`);
}
