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
import { generateBriefAsync } from "../services/brief-generator.js";
import { publishToWordPress } from "../services/wp-publisher.js";

export async function generateRoutes(app: FastifyInstance): Promise<void> {
  const server = app.withTypeProvider<ZodTypeProvider>();

  // POST /generate - start a new job
  server.post("/generate", {
    schema: {
      tags: ["jobs"],
      body: GenerateRequestSchema,
      response: { 202: z.object({ job_id: z.string().uuid(), brief: ContentBriefSchema }) },
    },
  }, async (request, reply) => {
    const { category, productUrl, site } = request.body;
    const brief = await generateBriefAsync(category, productUrl, site);
    if ("error" in brief) return reply.code(400).send(brief);
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

  // POST /generate/:job_id/publish - insert placements, convert to HTML, publish to WordPress
  server.post("/generate/:job_id/publish", {
    schema: {
      tags: ["jobs"],
      params: z.object({ job_id: z.string() }),
      body: PublishRequestSchema,
      response: {
        200: PublishResultSchema,
        404: z.object({ error: z.string() }),
        500: z.object({ error: z.string() }),
      },
    },
  }, async (request, reply) => {
    const { job_id } = request.params;
    const { article, site, status, placements, seo } = request.body;
    const job = jobStore.get(job_id);
    if (!job?.brief) return reply.code(404).send({ error: "Job not found" });

    try {
      const publishResult = await publishToWordPress({
        jobId: job_id,
        article,
        brief: job.brief,
        siteKey: site,
        status,
        placements,
        seo,
      });
      jobStore.update(job_id, { status: "published", publishResult });
      return reply.send(publishResult);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      jobStore.update(job_id, { status: "failed" });
      return reply.code(500).send({ error: msg });
    }
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
