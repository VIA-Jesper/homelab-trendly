import Fastify from "fastify";
import {
  jsonSchemaTransform, serializerCompiler, validatorCompiler,
} from "fastify-type-provider-zod";
import swagger from "@fastify/swagger";
import swaggerUi from "@fastify/swagger-ui";
import { generateRoutes } from "./routes/generate.js";

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

// Serve raw OpenAPI spec (enables MCP wrapping via @ivotoby/openapi-mcp-server)
app.get("/openapi.json", async (_req, reply) => reply.send(app.swagger()));

const PORT = Number(process.env["PORT"] ?? 3000);
await app.listen({ port: PORT, host: "0.0.0.0" });
console.log(`🚀 Trendly API   http://localhost:${PORT}`);
console.log(`📄 OpenAPI spec  http://localhost:${PORT}/openapi.json`);
console.log(`🔍 Swagger UI    http://localhost:${PORT}/docs`);
