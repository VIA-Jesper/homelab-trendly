import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

const client = new Client({ name: "owl", version: "1.0" });
const transport = new StreamableHTTPClientTransport(new URL("http://localhost:3001/mcp"));
await client.connect(transport);
console.log("Connected to MCP server");

// List available tools
const tools = await client.listTools();
console.log("\n=== AVAILABLE TOOLS ===");
for (const t of tools.tools) {
  console.log(`  ${t.name}: ${t.description?.substring(0, 80)}`);
}

// Try get_brief with different categories
const categories = ["robotstøvsugere", "kaffemaskiner", "havemaskiner", "grill"];
for (const cat of categories) {
  console.log(`\n=== get_brief: ${cat} ===`);
  try {
    const result = await client.callTool({
      name: "get_brief",
      arguments: { category: cat, site: "husforbegyndere" }
    });
    const text = result.content[0]?.text || JSON.stringify(result);
    console.log(text.substring(0, 500));
  } catch (e) {
    console.log(`Error: ${e.message}`);
  }
}

await client.close();
