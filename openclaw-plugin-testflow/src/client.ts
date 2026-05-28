const BASE_URL = process.env.TESTFLOW_TOOL_SERVER ?? "http://localhost:8000";

export async function callTool(path: string, body: unknown): Promise<unknown> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`TestFlow tool server error: ${res.status} ${await res.text()}`);
  }
  return res.json();
}

export async function getTool(path: string): Promise<unknown> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`TestFlow tool server error: ${res.status}`);
  }
  return res.json();
}
