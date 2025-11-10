import React, { useMemo, useState } from "react";
import styles from "./Verify.module.css";

const API_BASE = (process.env.REACT_APP_API_BASE || "").replace(/\/+$/, "");
const PATH = "/verify_identity";

function mask(nid?: string) {
  if (!nid) return "-";
  return nid.length < 5 ? nid : nid.replace(/.(?=.{4})/g, "*");
}

type Status = "idle" | "success" | "warn" | "error";

export default function Verify() {
  const [country, setCountry] = useState("SE");
  const [nid, setNid] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>("idle");

  const placeholder = useMemo(() => {
    switch (country) {
      case "DK": return "010170-1234";
      case "SE": return "19800101-1230";
      case "NO": return "010170 12345";
      case "FI": return "010170-123A";
      default:   return "National ID";
    }
  }, [country]);

  async function onCheck() {
    const nationalId = nid.trim();
    if (!nationalId) { setMsg("Please enter a national ID."); setStatus("warn"); return; }

    setMsg("Checking…"); setStatus("idle"); setBusy(true);
    try {
      const r = await fetch(`${API_BASE}${PATH}`, {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country, nationalId }),
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);

      const data = await r.json();
      const out = typeof (data as any)?.body === "string"
        ? JSON.parse((data as any).body)
        : data;

      const s = String(out.status || "").toUpperCase();
      const rec = out.registry_record || {};
      const id  = rec.national_id || rec.nationalId || nationalId;
      const cty = out.country || out.source || country;

      if (s === "VERIFIED") {
        setMsg(`✅ ${rec.firstName || "-"} ${rec.lastName || "-"} is registered in ${cty} • ID ${mask(id)}`);
        setStatus("success");
      } else if (s === "MISMATCH") {
        setMsg(`⚠️ Data mismatch. ${out.reason || ""}`.trim());
        setStatus("warn");
      } else if (s === "NOT_FOUND") {
        setMsg(`❌ Not found in ${cty} • ID ${mask(id)}`);
        setStatus("error");
      } else if (s === "ERROR") {
        setMsg(`⚠️ ${out.reason || "Unexpected error."}`);
        setStatus("error");
      } else {
        if (typeof out.registered === "boolean") {
          if (out.registered) {
            setMsg(`✅ ${out.firstName || "-"} ${out.lastName || "-"} is registered in ${out.country || cty} • ID ${mask(out.nationalId || id)}`);
            setStatus("success");
          } else {
            setMsg(`❌ Not registered in ${out.country || cty} • ID ${mask(out.nationalId || id)}`);
            setStatus("error");
          }
        } else {
          setMsg(`⚠️ Unexpected response shape.`);
          setStatus("warn");
        }
      }
    } catch (e: any) {
      setMsg(`Error: ${e?.message || String(e)}`);
      setStatus("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Verify Registration</h1>

      <div className={styles.card}>
        <div className={styles.formRow}>
          <label className={styles.label}>
            Country
            <select
              className={styles.select}
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              disabled={busy}
            >
              <option value="DK">Denmark</option>
              <option value="SE">Sweden</option>
              <option value="NO">Norway</option>
              <option value="FI">Finland</option>
            </select>
          </label>

          <input
            className={styles.input}
            placeholder={placeholder}
            value={nid}
            onChange={(e) => setNid(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") onCheck(); }}
            disabled={busy}
          />

          <button className={styles.btn} onClick={onCheck} disabled={busy}>
            {busy ? "Verifying…" : "Verify"}
          </button>
        </div>

        <div className={styles.helpRow}>
          <span className={styles.badge}>{country}</span>
          <span className={styles.hint}>Use the national ID format shown as placeholder.</span>
        </div>

        {msg && (
          <div
            className={`${styles.result} ${
              status === "success" ? styles.success
              : status === "warn" ? styles.warn
              : status === "error" ? styles.error
              : ""
            }`}
          >
            {msg}
          </div>
        )}
      </div>
    </div>
  );
}
