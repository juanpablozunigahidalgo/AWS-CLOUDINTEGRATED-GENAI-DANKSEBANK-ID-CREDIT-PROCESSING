// src/lib/agent.ts
export type AgentReply = { reply: string; sessionId?: string };

const AGENT_API =
  (import.meta as any).env?.VITE_AGENT_API ||
  (process as any).env?.REACT_APP_AGENT_API ||
  "https://wuw2m3dxvqvictakeqarwenn740veslt.lambda-url.eu-central-1.on.aws/";

// Keep a stable session across messages
function getSessionId(): string {
  const k = "agent_session_id";
  let v = localStorage.getItem(k);
  if (!v) {
    v = crypto.randomUUID().replace(/-/g, "");
    localStorage.setItem(k, v);
  }
  return v;
}

export async function chatWithAgent(message: string): Promise<AgentReply> {
  const sessionId = getSessionId();

  const res = await fetch(AGENT_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-session-id": sessionId,
    },
    body: JSON.stringify({ message, sessionId }),
  });

  const contentType = res.headers.get("Content-Type") || "";
  const raw = contentType.includes("application/json") ? await res.json() : await res.text();

  if (!res.ok) {
    const errText = typeof raw === "string" ? raw : JSON.stringify(raw);
    throw new Error(errText);
  }

  // IMPORTANTE:
  // Devolvemos SIEMPRE el payload completo como string.
  // El parser de upload buscará {"event":"upload_request", ...} en cualquier parte del texto.
  const full = typeof raw === "string" ? raw : JSON.stringify(raw);
  return { reply: full, sessionId };
}
