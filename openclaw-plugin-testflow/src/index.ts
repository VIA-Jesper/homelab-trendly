import { Type } from "@sinclair/typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { callTool, getTool } from "./client.js";

export default definePluginEntry({
  id: "testflow",
  name: "TestFlow Affiliate Pipeline",
  description: "Fetch products, run compliance checks, and publish WP drafts for the affiliate pipeline.",

  register(api) {
    // ── Fetch products from PriceRunner ────────────────────────────────────
    api.registerTool({
      name: "testflow_fetch_products",
      label: "Fetch PriceRunner Products",
      description: "Fetch product data for a PriceRunner category. Returns products with affiliate URLs.",
      parameters: Type.Object({
        category_id: Type.Number({ description: "Numeric PriceRunner category ID." }),
        limit: Type.Optional(Type.Number({ description: "Max products (default 10)." })),
        explicit_products: Type.Optional(Type.Array(Type.String(), {
          description: "Filter to these product names only (for versus/single-review).",
        })),
      }),
      execute: ({ category_id, limit, explicit_products }) =>
        callTool("/tools/fetch_products", { category_id, limit, explicit_products }),
    });

    // ── Inject compliance transforms into HTML ─────────────────────────────
    api.registerTool({
      name: "testflow_inject_compliance",
      label: "Inject Compliance",
      description: "Add affiliate disclosure, ?ref-site= params, and widget to article HTML.",
      parameters: Type.Object({
        html: Type.String({ description: "Raw article body HTML." }),
        affiliate_id: Type.String({ description: "PriceRunner ref-site ID." }),
        partner_id: Type.String({ description: "PriceRunner partnerId for widget." }),
      }),
      execute: ({ html, affiliate_id, partner_id }) =>
        callTool("/tools/inject_compliance", { html, affiliate_id, partner_id }),
    });

    // ── Deterministic safety audit ─────────────────────────────────────────
    api.registerTool({
      name: "testflow_deterministic_audit",
      label: "Deterministic Audit",
      description: "Run rule-based compliance checks on article HTML. Returns passed/errors/warnings.",
      parameters: Type.Object({
        html: Type.String({ description: "Article HTML to audit." }),
      }),
      execute: ({ html }) => callTool("/tools/deterministic_audit", { html }),
    });

    // ── Create WordPress draft (requires approval) ─────────────────────────
    api.registerTool({
      name: "testflow_create_draft",
      label: "Create WP Draft",
      description: "Publish the article as a WordPress draft. REQUIRES HUMAN APPROVAL before executing.",
      optional: true,
      parameters: Type.Object({
        article: Type.Object({
          title: Type.String(),
          slug: Type.String(),
          body_html: Type.String(),
          yoast_meta: Type.Object({
            focus_keyword: Type.String(),
            seo_title: Type.String(),
            meta_description: Type.String(),
          }),
          categories: Type.Array(Type.String()),
          tags: Type.Array(Type.String()),
          featured_image_url: Type.Optional(Type.String()),
        }),
        site: Type.String({ description: "Site config path, e.g. sites/site-one.yaml." }),
      }),
      execute: ({ article, site }) => callTool("/tools/create_draft", { article, site }),
    });

    // ── Record pipeline run in SQLite ──────────────────────────────────────
    api.registerTool({
      name: "testflow_record_run",
      label: "Record Run",
      description: "Save pipeline run metadata to the SQLite state database.",
      parameters: Type.Object({
        run_id: Type.String(),
        topic: Type.String(),
        keyword: Type.String(),
        category_id: Type.Number(),
        article_type: Type.String(),
        status: Type.String({ description: "success|aborted|failed" }),
        stats: Type.Optional(Type.Object({}, { additionalProperties: true })),
      }),
      execute: (params) => callTool("/tools/record_run", params),
    });

    // ── Get published article titles for internal linking ──────────────────
    api.registerTool({
      name: "testflow_published_titles",
      label: "Published Titles",
      description: "Get titles of published articles on a site (for internal linking in SEO pass).",
      parameters: Type.Object({
        site_name: Type.String(),
        limit: Type.Optional(Type.Number()),
      }),
      execute: ({ site_name, limit }) =>
        getTool(`/tools/published_titles?site_name=${site_name}${limit ? `&limit=${limit}` : ""}`),
    });

    // ── Discover PriceRunner categories ────────────────────────────────────
    api.registerTool({
      name: "testflow_discover_categories",
      label: "Discover Categories",
      description: "Search PriceRunner's category tree for a product type. Returns category names and numeric IDs. Call this when a product category is not in pricerunner-categories.yaml.",
      parameters: Type.Object({
        query: Type.String({ description: "Product type to search for, in Danish (e.g. 'robotstøvsugere', 'kaffemaskiner')" }),
      }),
      execute: ({ query }) => callTool("/tools/discover_categories", { query }),
    });

    // ── Approval gate: pause before creating WP draft ─────────────────────
    api.on("before_tool_call", async (event) => {
      if (event.toolName !== "testflow_create_draft") return;

      const article = event.params.article as { title: string };
      return {
        requireApproval: {
          title: "Create WordPress Draft",
          description: `About to create WP draft: "${article.title}"\n\nApprove to publish to WordPress. Deny to abort without publishing.`,
          severity: "info",
          timeoutMs: 300_000,
          timeoutBehavior: "deny",
        },
      };
    });
  },
});
