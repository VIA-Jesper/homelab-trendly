import type { FastifyInstance } from "fastify";
import type { ZodTypeProvider } from "fastify-type-provider-zod";
import { z } from "zod";
import { v4 as uuidv4 } from "uuid";
import {
  GenerateRequestSchema, PublishRequestSchema,
  ContentBriefSchema, PublishResultSchema, JobStatusSchema,
} from "../types/index.js";
import type { Job } from "../types/index.js";
import { jobStore } from "../store/job-store.js";
import { generateBrief } from "../services/brief-generator.js";
import { validateArticle } from "../services/validator.js";
import { insertWidgets } from "../services/widget-inserter.js";
// Phase 1: write to disk. Phase 2: swap this import for wp-publisher.ts
import { writeArticleToFile } from "../services/file-writer.js";

export async function generateRoutes(app: FastifyInstance): Promise<void> {
  const server = app.withTypeProvider<ZodTypeProvider>();

  // POST /generate — start a new job
  server.post("/generate", {
    schema: {
      tags: ["jobs"],
      body: GenerateRequestSchema,
      response: { 202: z.object({ job_id: z.string().uuid(), brief: ContentBriefSchema }) },
    },
  }, async (request, reply) => {
    const { category, productUrl, site } = request.body;
    const brief = generateBrief(category, productUrl, site);
    const job: Job = {
      job_id: uuidv4(), status: "briefed", brief,
      createdAt: new Date(), updatedAt: new Date(),
    };
    jobStore.set(job);
    return reply.code(202).send({ job_id: job.job_id, brief });
  });

  // GET /generate/:job_id/brief
  server.get("/generate/:job_id/brief", {
    schema: {
      tags: ["jobs"],
      params: z.object({ job_id: z.string() }),
      response: {
        200: ContentBriefSchema,
        404: z.object({ error: z.string() }),
      },
    },
  }, async (request, reply) => {
    const { job_id } = request.params;
    const job = jobStore.get(job_id);
    if (!job?.brief) return reply.code(404).send({ error: "Job not found" });
    return reply.send(job.brief);
  });

  // POST /generate/:job_id/publish — validate, insert widgets, write to disk
  server.post("/generate/:job_id/publish", {
    schema: {
      tags: ["jobs"],
      params: z.object({ job_id: z.string() }),
      body: PublishRequestSchema,
      response: {
        200: PublishResultSchema,
        404: z.object({ error: z.string() }),
      },
    },
  }, async (request, reply) => {
    const { job_id } = request.params;
    const { article } = request.body;
    const job = jobStore.get(job_id);
    if (!job?.brief) return reply.code(404).send({ error: "Job not found" });
    const validation = validateArticle(article, job.brief);
    const articleWithWidgets = insertWidgets(validation.article_with_placeholders, job.brief);
    // Phase 1: write to disk. Phase 2: swap for publishToWordPress(...)
    const publishResult = writeArticleToFile({
      jobId: job_id, article: articleWithWidgets, brief: job.brief, validation,
    });
    jobStore.update(job_id, { status: "published", publishResult });
    return reply.send(publishResult);
  });

  // GET /generate/:job_id/status
  server.get("/generate/:job_id/status", {
    schema: {
      tags: ["jobs"],
      params: z.object({ job_id: z.string() }),
      response: {
        200: z.object({ job_id: z.string(), status: JobStatusSchema }),
        404: z.object({ error: z.string() }),
      },
    },
  }, async (request, reply) => {
    const { job_id } = request.params;
    const job = jobStore.get(job_id);
    if (!job) return reply.code(404).send({ error: "Job not found" });
    return reply.send({ job_id: job.job_id, status: job.status });
  });
}
