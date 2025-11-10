import { useEffect, useRef, useState, useCallback } from "react";
import { chatWithAgent } from "../lib/agent";
import styles from "./AgentChatWidget.module.css";
import avatar from "./Avatar.png";

import UploadModal from "./UploadModal";

type Msg = { role: "user" | "agent"; text: string };

// Lee el bucket para incluirlo en el mensaje al agente
const S3_BUCKET =
  (import.meta as any).env?.VITE_S3_BUCKET ||
  (process as any).env?.REACT_APP_S3_BUCKET ||
  "db-onboard-uploads";

export default function AgentChatWidget({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  // 👉 nuevo estado: modal + sessionId local del FE (para la key en S3)
  const [showUpload, setShowUpload] = useState(false);
  const [clientSessionId, setClientSessionId] = useState<string | null>(null);
  // opcional: si quieres incluir el país en la key de S3
  const [country] = useState<"DK" | "SE" | "NO" | "FI" | "">("");

  // Refs utilitarias
  const bodyRef = useRef<HTMLDivElement>(null);
  const inFlightRef = useRef(false); // evita envíos simultáneos
  const lastReplySigRef = useRef<string | null>(null); // dedup de respuestas

  /* ---------------- Ciclo de vida ---------------- */

  useEffect(() => {
    if (!open) {
      setMessages([]);
      setInput("");
      setShowUpload(false);
      setClientSessionId(null);
      lastReplySigRef.current = null;
      inFlightRef.current = false;
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [open, onClose]);

  useEffect(() => {
    bodyRef.current?.scrollTo({
      top: bodyRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, showUpload]);

  /* ---------------- Core: enviar y procesar respuesta ---------------- */

  function sigOf(val: unknown): string {
    const s = typeof val === "string" ? val : JSON.stringify(val ?? "");
    return `${s.length}:${s.slice(0, 160)}:${s.slice(-160)}`;
  }

  const append = useCallback((m: Msg) => {
    setMessages((prev) => [...prev, m]);
  }, []);

  async function send(textArg?: string) {
    const text = (textArg ?? input).trim();
    if (!text) return;
    if (loading || inFlightRef.current) return;

    inFlightRef.current = true;
    setLoading(true);
    append({ role: "user", text });
    if (!textArg) setInput("");

    try {
      const { reply } = await chatWithAgent(text);
      const raw = typeof reply === "string" ? reply : JSON.stringify(reply);
      const sig = sigOf(raw);

      if (lastReplySigRef.current === sig) {
        console.debug("[AgentChatWidget] duplicate reply skipped");
        return;
      }
      lastReplySigRef.current = sig;

      console.debug("[AgentChatWidget] raw reply:", raw);

      // Intentar extraer el texto “humano” de la respuesta
      let assistantText = raw;
      try {
        const asJson = JSON.parse(raw);
        if (asJson && typeof asJson.reply === "string") assistantText = asJson.reply;
      } catch {
        /* no-op: viene como texto plano */
      }

      // 🚩 Frase-gatillo del agente
      const TRIGGER = "Please upload your ID card using this link.";
      if (assistantText.includes(TRIGGER)) {
        const sid = crypto.randomUUID(); // sessionId local del FE
        setClientSessionId(sid);
        setShowUpload(true);

        append({
          role: "agent",
          text:
            "Opening the upload dialog now. Once finished, I’ll continue.",
        });
      } else {
        append({ role: "agent", text: assistantText || "" });
      }
    } catch (e: any) {
      append({ role: "agent", text: `⚠️ ${e?.message || "Network error"}` });
    } finally {
      setLoading(false);
      inFlightRef.current = false;
    }
  }

  // El modal ahora devuelve (sessionId, key)
  async function handleUploaded(finalSessionId: string, key: string) {
    console.debug("[AgentChatWidget] file uploaded, notifying agent…", {
      finalSessionId,
      key,
      bucket: S3_BUCKET,
    });

    const msg =
      `I have uploaded my ID. ` +
      `[sessionId:${finalSessionId}] ` +
      `[bucket:${S3_BUCKET}] ` +
      `[key:${key}]`;

    await send(msg);
    setShowUpload(false);
  }

  const uiMessages = messages;

  if (!open) return null;

  /* ---------------- Render ---------------- */

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>
          <div className={styles.titleBox}>
            <img className={styles.avatar} src={avatar} alt="Assistant" />
            <div>
              <div className={styles.title}>Onboarding Agent</div>
              <div className={styles.sub}>Danske Bank • AI assistant</div>
            </div>
          </div>
          <button className={styles.close} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <div ref={bodyRef} className={styles.body}>
          {uiMessages.length === 0 && (
            <div className={styles.empty}>
              <div className={styles.emptyIcon}>💬</div>
              <div>Ask me anything about onboarding.</div>
            </div>
          )}
          {uiMessages.map((m, i) => (
            <div
              key={i}
              className={`${styles.msg} ${styles[m.role === "user" ? "user" : "agent"]}`}
              style={{ whiteSpace: "pre-wrap" }}
            >
              {m.text}
            </div>
          ))}
          {loading && <div className={`${styles.msg} ${styles.agent}`}>…</div>}
        </div>

        <div className={styles.footer}>
          <input
            className={styles.input}
            placeholder="Type a message…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (!loading && !inFlightRef.current) send();
              }
            }}
            autoFocus
            disabled={loading}
          />
          <button
            className={styles.send}
            onClick={() => !loading && !inFlightRef.current && send()}
            disabled={loading || !input.trim()}
            type="button"
          >
            Send
          </button>
        </div>
      </div>

      <UploadModal
        open={showUpload}
        onClose={() => setShowUpload(false)}
        mode="s3Direct"
        clientSessionId={clientSessionId || undefined}
        country={country || undefined}
        onUploaded={(sid, key) => handleUploaded(sid, key)} // 👈 ahora recibe sid y key
      />
    </div>
  );
}
