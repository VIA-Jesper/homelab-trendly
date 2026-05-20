import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    environment: "node",
    // Resolve .js imports to .ts files (required for NodeNext + vitest)
    alias: [
      { find: /^(\..+)\.js$/, replacement: "$1" },
    ],
  },
});
