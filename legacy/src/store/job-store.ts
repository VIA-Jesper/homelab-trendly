import type { Job } from "../types/index.js";

class JobStore {
  private readonly store = new Map<string, Job>();

  set(job: Job): void {
    this.store.set(job.job_id, job);
  }

  get(jobId: string): Job | undefined {
    return this.store.get(jobId);
  }

  update(jobId: string, patch: Partial<Job>): Job | undefined {
    const existing = this.store.get(jobId);
    if (!existing) return undefined;
    const updated: Job = { ...existing, ...patch, updatedAt: new Date() };
    this.store.set(jobId, updated);
    return updated;
  }

  has(jobId: string): boolean {
    return this.store.has(jobId);
  }

  all(): Job[] {
    return Array.from(this.store.values());
  }
}

export const jobStore = new JobStore();
