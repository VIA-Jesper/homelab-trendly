import Fastify from "fastify";
import { readFileSync, existsSync, readdirSync, statSync } from "fs";
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

function findMostRecentArticle(): { articlePath: string; briefPath: string } {
  const promptsDir = resolve("prompts");
  const files = readdirSync(promptsDir)
    .filter(f => f.startsWith("article-") && f.endsWith(".json"))
    .map(f => {
      const stat = statSync(resolve(promptsDir, f));
      return { name: f, mtime: stat.mtimeMs };
    })
    .sort((a, b) => b.mtime - a.mtime);

  if (files.length === 0) {
    return {
      articlePath: resolve("prompts/article-robotstovsugere-sample.json"),
      briefPath: resolve("prompts/brief-robotstovsugere-sample.json")
    };
  }

  const articleFile = files[0].name;
  const articlePath = resolve(promptsDir, articleFile);
  // Try to find matching brief: brief-{same-suffix}.json, fall back to brief-{category}-sample.json
  const suffix = articleFile.replace(/^article-/, "").replace(/\.json$/, "");
  let briefPath = resolve(promptsDir, `brief-${suffix}.json`);
  if (!existsSync(briefPath)) {
    // Extract category (everything before last hyphen if it ends in -sample, -regen, etc.)
    const categoryMatch = suffix.match(/^(.+?)(?:-[\w]+)$/);
    const category = categoryMatch ? categoryMatch[1] : suffix;
    briefPath = resolve(promptsDir, `brief-${category}-sample.json`);
    if (!existsSync(briefPath)) {
      briefPath = resolve("prompts/brief-robotstovsugere-sample.json");
    }
  }

  return { articlePath, briefPath };
}

fastify.get("/", async (request, reply) => {
  try {
    const q = request.query as any;

    let articlePath: string;
    let briefPath: string;

    if (q.slug) {
      // Explicit slug requested
      articlePath = resolve(`prompts/article-${q.slug}.json`);
      briefPath = resolve(`prompts/brief-${q.slug}.json`);
      if (!existsSync(briefPath)) {
        // Try to derive category from slug and find matching brief
        const categoryMatch = q.slug.match(/^(.+?)(?:-[\w]+)$/);
        const category = categoryMatch ? categoryMatch[1] : q.slug;
        briefPath = resolve(`prompts/brief-${category}-sample.json`);
        if (!existsSync(briefPath)) {
          briefPath = resolve("prompts/brief-robotstovsugere-sample.json");
        }
      }
    } else if (q.category) {
      // Category specified
      articlePath = resolve(`prompts/article-${q.category}-sample.json`);
      briefPath = resolve(`prompts/brief-${q.category}-sample.json`);
    } else {
      // Root path: show most recent article
      const recent = findMostRecentArticle();
      articlePath = recent.articlePath;
      briefPath = recent.briefPath;
    }

    if (!existsSync(articlePath)) {
      articlePath = resolve("prompts/article-robotstovsugere-sample.json");
      briefPath = resolve("prompts/brief-robotstovsugere-sample.json");
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
