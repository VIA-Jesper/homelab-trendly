import Fastify from "fastify";
import {
  jsonSchemaTransform, serializerCompiler, validatorCompiler,
} from "fastify-type-provider-zod";
import swagger from "@fastify/swagger";
import swaggerUi from "@fastify/swagger-ui";
import { generateRoutes } from "./routes/generate.js";
import { startMcpServer } from "./mcp/server.js";

const app = Fastify({ logger: { level: process.env["LOG_LEVEL"] ?? "info" } });

app.setValidatorCompiler(validatorCompiler);
app.setSerializerCompiler(serializerCompiler);

await app.register(swagger, {
  openapi: {
    openapi: "3.1.0",
    info: {
      title: "Trendly API",
      version: "1.0.0",
      description: "MCP-compatible content brief API for AI-assisted affiliate article generation.",
    },
    servers: [{ url: `http://localhost:${process.env["PORT"] ?? 3000}` }],
  },
  transform: jsonSchemaTransform,
});

await app.register(swaggerUi, {
  routePrefix: "/docs",
  uiConfig: { docExpansion: "list" },
});

await app.register(generateRoutes);

// Serve raw OpenAPI spec
app.get("/openapi.json", async (_req, reply) => reply.send(app.swagger()));

// Health probe - used by Docker healthcheck, K8s readiness probe, hosted platforms
app.get("/health", async (_req, reply) => reply.send({
  status: "ok",
  uptime: Math.floor(process.uptime()),
  version: "1.0.0",
}));

// MCP discovery endpoint
app.get("/mcp-info", async (_req, reply) => reply.send({
  mcpPort: Number(process.env["MCP_PORT"] ?? 3001),
  transport: "streamable-http",
  endpoint: "/mcp",
  tools: ["get_brief", "validate_article", "publish_article"],
}));

const PORT = Number(process.env["PORT"] ?? 3000);
await app.listen({ port: PORT, host: "0.0.0.0" });
console.log(`🚀 Trendly API   http://localhost:${PORT}`);
console.log(`📄 OpenAPI spec  http://localhost:${PORT}/openapi.json`);
console.log(`🔍 Swagger UI    http://localhost:${PORT}/docs`);

// Start MCP server on port 3001
await startMcpServer();
