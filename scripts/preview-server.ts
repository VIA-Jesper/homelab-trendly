import Fastify from "fastify";
import { readFileSync, existsSync } from "fs";
import { resolve } from "path";
import { insertPlacements } from "../src/services/widget-inserter.js";
import { convertMarkdownToHtml, insertAffiliateLinks } from "../src/services/affiliate-linker.js";
import type { ContentBrief, Placement } from "../src/types/index.js";

const fastify = Fastify({ logger: false });
const PORT = 3030;

function loadArticle(path: string) {
  const raw = readFileSync(resolve(path), "utf-8");
  try {
    return JSON.parse(raw);
  } catch {
    const fixed = raw.replace(/"article":\s*"([\s\S]*?)",\s*"placements"/, (_m, content) => {
      const escaped = content
        .replace(/\n/g, "\\n")
        .replace(/\r/g, "\\r")
        .replace(/\t/g, "\\t");
      return `"article": "${escaped}", "placements"`;
    });
    return JSON.parse(fixed);
  }
}

// Simple but beautiful Tailwind-based layout
const HTML_TEMPLATE = (title: string, content: string) => `
  <!DOCTYPE html>
  <html lang="da">
  <head>
    <meta charset="UTF-8">
    <title>Preview: ${title}</title>
    <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
      body { font-family: 'Inter', sans-serif; }
      .price-widget {
        @apply border rounded-xl p-6 my-8 flex items-center justify-between bg-white shadow-sm hover:shadow-md transition-shadow;
      }
      .price-widget .price { @apply text-2xl font-bold text-orange-600; }
      .price-widget .buy-btn { @apply bg-blue-600 text-white px-6 py-2 rounded-lg font-semibold hover:bg-blue-700 transition-colors; }
      figcaption { @apply text-center text-sm text-gray-500 mt-2 italic; }
      figure img { @apply mx-auto rounded-lg shadow-sm; }
    </style>
  </head>
  <body class="bg-gray-50 py-12 px-4">
    <div class="mx-auto max-w-3xl bg-white p-12 rounded-2xl shadow-sm border border-gray-100">
      <article class="prose prose-slate prose-lg max-w-none prose-headings:font-bold prose-a:text-blue-600">
        ${content}
      </article>
    </div>
  </body>
  </html>
`;

fastify.get("/", async (request, reply) => {
  try {
    const q = request.query as any;

    // Priority 1: explicit slug param (e.g. ?slug=robotstovsugere-hero)
    // Loads prompts/article-{slug}.json + prompts/brief-{slug}.json
    // Priority 2: category param (e.g. ?category=robotstovsugere)
    // Loads prompts/article-{category}-sample.json + prompts/brief-{category}-sample.json
    // Priority 3: fallback to robotstovsugere sample
    let articlePath: string;
    let briefPath: string;

    if (q.slug) {
      articlePath = resolve(`prompts/article-${q.slug}.json`);
      briefPath   = resolve(`prompts/brief-${q.slug}.json`);
    } else {
      const category = q.category || "robotstovsugere";
      articlePath = resolve(`prompts/article-${category}-sample.json`);
      briefPath   = resolve(`prompts/brief-${category}-sample.json`);
    }

    if (!existsSync(articlePath)) {
      articlePath = resolve("prompts/article-robotstovsugere-sample.json");
      briefPath   = resolve("prompts/brief-robotstovsugere-sample.json");
    }

    const articleData = loadArticle(articlePath);
    const briefData = JSON.parse(readFileSync(briefPath, "utf-8"));
    const brief = briefData.brief;
    const siteKey = articleData.site || "techblog";

    // Run the pipeline
    const withPlacements = insertPlacements(articleData.article, brief, articleData.placements, siteKey);
    const htmlBody = convertMarkdownToHtml(withPlacements);
    const { html: finalHtml } = insertAffiliateLinks(htmlBody, brief, siteKey);

    reply.type("text/html").send(HTML_TEMPLATE(articleData.seo.title, finalHtml));
  } catch (err: any) {
    reply.status(500).send({ error: "Failed to render preview", details: err.message });
  }
});

const start = async () => {
  try {
    await fastify.listen({ port: PORT, host: "0.0.0.0" });
    console.log(`\n🚀 Preview server running at http://localhost:${PORT}`);
    console.log(`Press Ctrl+C to stop.\n`);
  } catch (err) {
    fastify.log.error(err);
    process.exit(1);
  }
};

start();
