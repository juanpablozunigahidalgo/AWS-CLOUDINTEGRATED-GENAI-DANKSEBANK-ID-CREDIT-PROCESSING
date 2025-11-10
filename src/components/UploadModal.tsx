import { useCallback, useRef, useState } from "react";
import styles from "./AgentChatWidget.module.css";

// AWS SDK v3
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { fromCognitoIdentityPool } from "@aws-sdk/credential-providers";

/**
 * Variables de entorno:
 *  - VITE_AWS_REGION / REACT_APP_AWS_REGION          (ej: eu-central-1)
 *  - VITE_IDENTITY_POOL_ID / REACT_APP_IDENTITY_POOL_ID
 *  - VITE_S3_BUCKET / REACT_APP_S3_BUCKET
 */
const AWS_REGION =
  (import.meta as any).env?.VITE_AWS_REGION ||
  (process as any).env?.REACT_APP_AWS_REGION ||
  "eu-central-1";

const IDENTITY_POOL_ID =
  (import.meta as any).env?.VITE_IDENTITY_POOL_ID ||
  (process as any).env?.REACT_APP_IDENTITY_POOL_ID ||
  "";

const UPLOAD_BUCKET =
  (import.meta as any).env?.VITE_S3_BUCKET ||
  (process as any).env?.REACT_APP_S3_BUCKET ||
  "db-onboard-uploads";

type Props = {
  open: boolean;
  onClose: () => void;
  onUploaded?: (sessionId: string, key: string) => void; // 👈 ahora devuelve también el key

  // --- nuevo modo (por defecto) ---
  mode?: "s3Direct" | "presigned";
  clientSessionId?: string;
  country?: "DK" | "SE" | "NO" | "FI";

  // --- compat: si alguna vez quieres seguir usando presigned ---
  uploadUrl?: string;
  keyPrefix?: string;
  expiresInSeconds?: number;
  fields?: Record<string, string>;
};

const ALLOWED_TYPES = new Set(["image/jpeg", "image/png"]);
const DEFAULT_EXPIRES = 600;

/* ---------------- helpers S3 directo ---------------- */

function makeS3() {
  return new S3Client({
    region: AWS_REGION,
    credentials: fromCognitoIdentityPool({
      clientConfig: { region: AWS_REGION },
      identityPoolId: IDENTITY_POOL_ID,
    }),
  });
}

function buildS3Key(params: {
  country?: string;
  sessionId: string;
  fileName: string;
}) {
  const { country = "SE", sessionId, fileName } = params;
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  // estructura: onboard/SE/2025/11/09/<sessionId>/<nombre>
  return `onboard/${country}/${y}/${m}/${d}/${sessionId}/${fileName}`;
}

/* ---------------- componente ---------------- */

export default function UploadModal({
  open,
  onClose,
  onUploaded,
  mode = "s3Direct",
  clientSessionId,
  country,
  uploadUrl,
  keyPrefix,
  expiresInSeconds = DEFAULT_EXPIRES,
  fields,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string>("");

  const dropRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const validateFile = useCallback((f: File | null) => {
    if (!f) return "No file selected.";
    if (!ALLOWED_TYPES.has(f.type)) return "Only JPEG or PNG are allowed.";
    if (f.size > 10 * 1024 * 1024) return "Max file size is 10MB.";
    return "";
  }, []);

  const pick = (f: File | null) => {
    const err = validateFile(f);
    if (err) {
      setMsg(`⚠️ ${err}`);
      setFile(null);
      return;
    }
    setMsg("");
    setFile(f);
  };

  if (!open) return null;

  async function doUpload() {
    if (!file) return;
    setBusy(true);
    setMsg("");

    try {
      if (mode === "s3Direct") {
        if (!IDENTITY_POOL_ID) {
          throw new Error("Missing Identity Pool ID (VITE_IDENTITY_POOL_ID).");
        }
        const sessionId = clientSessionId || crypto.randomUUID();
        const key = buildS3Key({
          country,
          sessionId,
          fileName: file.name || "id_front.jpg",
        });

        const s3 = makeS3();

        // ✅ Fix: use Uint8Array to avoid readableStream.getReader error
        const buf = await file.arrayBuffer();

        await s3.send(
          new PutObjectCommand({
            Bucket: UPLOAD_BUCKET,
            Key: key,
            Body: new Uint8Array(buf),
            ContentType: file.type || "image/jpeg",
          })
        );

        setMsg(`✅ Uploaded to s3://${UPLOAD_BUCKET}/${key}`);
        setFile(null);
        setBusy(false);
        onUploaded?.(sessionId, key); // 👈 devolvemos sessionId y key
        return;
      }

      // --------- compat: presigned (si algún día lo quieres reusar) ---------
      if (fields && Object.keys(fields).length) {
        // Presigned POST
        const fd = new FormData();
        for (const [k, v] of Object.entries(fields)) fd.append(k, v);
        if (!("Content-Type" in fields) && !("content-type" in fields)) {
          fd.append("Content-Type", file.type || "image/jpeg");
        }
        fd.append("file", file);
        const res = await fetch(uploadUrl || "", { method: "POST", body: fd });
        if (!(res.status === 204 || res.status === 201)) {
          const text = await res.text().catch(() => "");
          throw new Error(
            `Upload failed (HTTP ${res.status}). ${
              text ? `Response: ${text.slice(0, 600)}` : ""
            }`
          );
        }
      } else {
        // Presigned PUT (necesitarías resolver URL aquí; omitido para mantener simple)
        throw new Error("Presigned PUT path is disabled in this build.");
      }

      setMsg("✅ ID uploaded successfully.");
      setFile(null);
      setBusy(false);
      onUploaded?.(clientSessionId || "", keyPrefix || "");
    } catch (err: any) {
      console.error("[UploadModal] Upload exception:", err);
      setMsg(`⚠️ ${err?.message || "Upload error"}`);
      setBusy(false);
    }
  }

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    dropRef.current?.classList.add("dragover");
  };
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dropRef.current?.classList.remove("dragover");
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    dropRef.current?.classList.remove("dragover");
    pick(e.dataTransfer.files?.[0] || null);
  };

  const onPickClick = () => inputRef.current?.click();
  const stopCloseIfBusy = (e: React.MouseEvent) => {
    if (busy) e.stopPropagation();
  };

  return (
    <div
      className={styles.overlay}
      onClick={busy ? undefined : onClose}
      aria-modal="true"
      role="dialog"
    >
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>
          <div className={styles.title}>Upload your ID</div>
          <button
            className={styles.close}
            onClick={busy ? stopCloseIfBusy : onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className={styles.body}>
          <p className={styles.sub}>
            We’ll upload your ID securely. (Expires in {expiresInSeconds} seconds)
          </p>

          {clientSessionId && (
            <p className={styles.sub}>
              Session ID: <code>{clientSessionId}</code>
            </p>
          )}

          <div
            ref={dropRef}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={styles.msg}
            style={{ cursor: "pointer" }}
            onClick={onPickClick}
          >
            Drag &amp; drop a JPEG/PNG here
          </div>

          <div style={{ margin: "8px 0" }}>
            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png"
              style={{ display: "none" }}
              onChange={(e) => pick(e.target.files?.[0] || null)}
              disabled={busy}
            />
            <button onClick={onPickClick} className={styles.send} disabled={busy}>
              Choose File
            </button>
            {file && (
              <span style={{ marginLeft: 8 }}>
                <strong>{file.name}</strong>{" "}
                <small>
                  ({file.type || "unknown"}, {file.size} bytes)
                </small>
              </span>
            )}
          </div>

          {msg && (
            <pre
              style={{
                marginTop: 8,
                whiteSpace: "pre-wrap",
                maxHeight: 220,
                overflow: "auto",
              }}
            >
              {msg}
            </pre>
          )}
        </div>

        <div className={styles.footer}>
          <button className={styles.send} onClick={doUpload} disabled={!file || busy}>
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
