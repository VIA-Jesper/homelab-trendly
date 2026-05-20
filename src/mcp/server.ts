import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { createServer } from "http";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { v4 as uuidv4 } from "uuid";
import { z } from "zod";
import { jobStore } from "../store/job-store.js";
import { generateBriefAsync } from "../services/brief-generator.js";
import { publishToWordPress } from "../services/wp-publisher.js";
import { logPublished } from "../services/duplicate-guard.js";
import { validateArticleFull } from "../services/validator.js";
import { discoverBestCategory } from "../services/category-discoverer.js";
import { PlacementSchema, SeoPayloadSchema } from "../types/index.js";
import type { Job } from "../types/index.js";

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
    version: "1.0.0",
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

      const jobId = uuidv4();
      const job: Job = {
        job_id: jobId,
        status: "briefed",
        brief: result,
        createdAt: new Date(),
        updatedAt: new Date(),
      };
      jobStore.set(job);

      const writingInstructions = loadWritingInstructions(result.articleType);
      return {
        content: [{
          type: "text" as const,
          text: JSON.stringify({ job_id: jobId, brief: result, writingInstructions }),
        }],
      };
    }
  );

  // ─── Tool: publish_article ───────────────────────────────────────────────
  server.tool(
    "publish_article",
    "Publish a Markdown article to WordPress. Injects widgets/images at specified placements, converts Markdown to HTML, adds affiliate links, and posts to WP.",
    {
      job_id: z.string().describe("The job_id returned by get_brief"),
      article: z.string().describe("Article content in Markdown"),
      site: z.string().describe("Site key, e.g. 'techblog'"),
      status: z.enum(["publish", "draft"]).describe("Whether to publish or save as draft"),
      placements: z.array(PlacementSchema).default([]).describe("Where to inject images/widgets"),
      seo: SeoPayloadSchema.optional().describe("SEO metadata for RankMath"),
    },
    async ({ job_id, article, site, status, placements, seo }) => {
      const job = jobStore.get(job_id);
      if (!job?.brief) {
        return {
          content: [{ type: "text" as const, text: JSON.stringify({ error: "job_not_found", job_id }) }],
          isError: true,
        };
      }

      try {
        const result = await publishToWordPress({
          jobId: job_id,
          article,
          brief: job.brief,
          siteKey: site,
          status,
          placements,
          seo,
        });
        if (status === "publish") {
          logPublished(
            site,
            job.brief.category,
            seo?.slug ?? job.brief.category,
            seo?.focus_keyword ?? "",
            job.brief.products.map((p) => p.id)
          );
        }
        jobStore.update(job_id, { status: "published" });
        return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        jobStore.update(job_id, { status: "failed" });
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
      job_id: z.string().describe("job_id from get_brief"),
      article: z.string().describe("Article content in Markdown"),
      placements: z.array(PlacementSchema).default([]).describe("Planned widget/image placements"),
    },
    async ({ job_id, article, placements }) => {
      const job = jobStore.get(job_id);
      if (!job?.brief) {
        return {
          content: [{ type: "text" as const, text: JSON.stringify({ error: "job_not_found", job_id }) }],
          isError: true,
        };
      }
      const result = validateArticleFull(article, job.brief, placements);
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
