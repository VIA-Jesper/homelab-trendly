import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

// ─── Mock fs before importing module ─────────────────────────────────────────
// The content-registry module reads/writes JSON files. We mock fs to keep tests
// fast and isolated from disk.
const mockFs = {
  readFileSync: vi.fn<[string, string], string>(),
  writeFileSync: vi.fn(),
  existsSync: vi.fn<[string], boolean>(),
  mkdirSync: vi.fn(),
  renameSync: vi.fn(),
};

vi.mock("fs", () => mockFs);

// Import AFTER mocking
const { isProductUsed, getUsedProductIds, registerProducts, resetCache } = await import(
  "../../src/services/content-registry.js"
);

describe("content-registry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetCache();
  });

  afterEach(() => {
    resetCache();
  });

  describe("isProductUsed", () => {
    it("returns false for unknown product when registry is empty", () => {
      mockFs.existsSync.mockReturnValue(false);
      expect(isProductUsed("techblog", "pr_123")).toBe(false);
    });

    it("returns false when product is not in registry", () => {
      mockFs.existsSync.mockReturnValue(true);
      mockFs.readFileSync.mockReturnValue(JSON.stringify({ techblog: ["pr_999"] }));
      expect(isProductUsed("techblog", "pr_123")).toBe(false);
    });

    it("returns true when product is in registry", () => {
      mockFs.existsSync.mockReturnValue(true);
      mockFs.readFileSync.mockReturnValue(JSON.stringify({ techblog: ["pr_123", "pr_456"] }));
      expect(isProductUsed("techblog", "pr_123")).toBe(true);
    });

    it("returns false for different site even if product is used on another", () => {
      mockFs.existsSync.mockReturnValue(true);
      mockFs.readFileSync.mockReturnValue(JSON.stringify({ techblog: ["pr_123"] }));
      expect(isProductUsed("budgetshop", "pr_123")).toBe(false);
    });
  });

  describe("getUsedProductIds", () => {
    it("returns empty array when no registry file exists", () => {
      mockFs.existsSync.mockReturnValue(false);
      expect(getUsedProductIds("techblog")).toEqual([]);
    });

    it("returns empty array for new site with no entries", () => {
      mockFs.existsSync.mockReturnValue(true);
      mockFs.readFileSync.mockReturnValue(JSON.stringify({ budgetshop: ["pr_1"] }));
      expect(getUsedProductIds("techblog")).toEqual([]);
    });
  });

  describe("registerProducts", () => {
    it("adds product IDs to an empty registry", () => {
      mockFs.existsSync.mockReturnValue(false);
      registerProducts("techblog", ["pr_100", "pr_200"]);

      expect(mockFs.writeFileSync).toHaveBeenCalledOnce();
      const written = mockFs.writeFileSync.mock.calls[0]![1] as string;
      const saved = JSON.parse(written) as Record<string, string[]>;
      expect(saved["techblog"]).toContain("pr_100");
      expect(saved["techblog"]).toContain("pr_200");
    });

    it("uses atomic write (writeFileSync to .tmp, then renameSync)", () => {
      mockFs.existsSync.mockReturnValue(false);
      registerProducts("techblog", ["pr_100"]);

      const writePath = mockFs.writeFileSync.mock.calls[0]![0] as string;
      const renameSrc = mockFs.renameSync.mock.calls[0]![0] as string;
      const renameDst = mockFs.renameSync.mock.calls[0]![1] as string;

      expect(writePath).toContain(".tmp");
      expect(renameSrc).toContain(".tmp");
      expect(renameDst).not.toContain(".tmp");
    });

    it("does not duplicate existing product IDs", () => {
      mockFs.existsSync.mockReturnValue(true);
      mockFs.readFileSync.mockReturnValue(JSON.stringify({ techblog: ["pr_100"] }));
      registerProducts("techblog", ["pr_100", "pr_200"]);

      const written = mockFs.writeFileSync.mock.calls[0]![1] as string;
      const saved = JSON.parse(written) as Record<string, string[]>;
      const ids = saved["techblog"]!;
      expect(ids.filter((id) => id === "pr_100")).toHaveLength(1);
    });

    it("does not write to disk when all products are already registered", () => {
      mockFs.existsSync.mockReturnValue(true);
      mockFs.readFileSync.mockReturnValue(JSON.stringify({ techblog: ["pr_100"] }));
      registerProducts("techblog", ["pr_100"]);
      expect(mockFs.writeFileSync).not.toHaveBeenCalled();
    });
  });
});
