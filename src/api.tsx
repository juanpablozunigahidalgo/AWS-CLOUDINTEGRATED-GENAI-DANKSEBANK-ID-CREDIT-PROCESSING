const API_BASE = process.env.REACT_APP_API_BASE || "";

export async function chatBedrock(input: {
  sessionId: string;
  country?: string;
  message: string;
}) {
  const r = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`chat ${r.status}`);
  return r.json() as Promise<{ reply: string; sessionId?: string }>;
}
