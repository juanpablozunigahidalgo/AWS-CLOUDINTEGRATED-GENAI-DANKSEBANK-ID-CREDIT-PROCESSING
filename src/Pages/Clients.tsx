import React, { useEffect, useMemo, useState } from "react";
import styles from "./Clients.module.css";

type Client = {
  firstName?: string;
  lastName?: string;
  email?: string;
  country?: "DK" | "SE" | "NO" | "FI" | string;
  nationalId?: string;
  createdAt?: string;
};

const API_BASE = (process.env.REACT_APP_API_BASE || "").replace(/\/+$/, "");
const COUNTRIES = ["DK", "SE", "NO", "FI"] as const;

function urlJoin(base: string, path: string, qs?: Record<string, string | number>) {
  const u = `${base}/${path.replace(/^\/+/, "")}`;
  if (!qs) return u;
  const p = new URL(u);
  Object.entries(qs).forEach(([k, v]) => p.searchParams.set(k, String(v)));
  return p.toString();
}
function fmtDate(iso?: string) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

export default function Clients() {
  const [items, setItems] = useState<Client[]>([]);
  const [apiCount, setApiCount] = useState<number | null>(null);
  const [status, setStatus] = useState("Loading…");
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState<"" | Client["country"]>("");
  const [page, setPage] = useState(1);

  const pageSize = 20;     // you said max 20 → perfect table page size
  const limit = 100;       // backend fetch cap

  const fetchClients = async () => {
    try {
      setLoading(true);
      setStatus("Loading…");
      const res = await fetch(urlJoin(API_BASE, "/clients", { limit }), { method: "GET", mode: "cors", headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      const payload = typeof (data as any)?.body === "string" ? JSON.parse((data as any).body) : data;
      const list: Client[] = Array.isArray(payload) ? payload : (payload.items ?? []);
      list.sort((a, b) => String(b.createdAt ?? "").localeCompare(String(a.createdAt ?? "")));
      setItems(list);
      setApiCount(Array.isArray(payload) ? list.length : (payload.count ?? list.length));
      setStatus(`Loaded ${list.length}${typeof payload.count === "number" ? ` of ${payload.count}` : ""} clients.`);
      setPage(1);
    } catch (e: any) {
      const msg = e?.message || "Failed to fetch";
      setStatus(msg.includes("Failed to fetch") ? "Error: Failed to fetch (CORS/API URL)" : `Error: ${msg}`);
      setItems([]);
      setApiCount(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchClients(); }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter(r => {
      if (country && r.country !== country) return false;
      if (!q) return true;
      const name = [r.firstName, r.lastName].filter(Boolean).join(" ").toLowerCase();
      return name.includes(q) || (r.email ?? "").toLowerCase().includes(q) || (r.nationalId ?? "").toLowerCase().includes(q);
    });
  }, [items, query, country]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageItems = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page]);

  return (
    <div className={styles.wrap}>
      <h1 className={styles.title}>Registered Clients</h1>

      <div className={styles.panel}>
        <div className={styles.toolbar}>
          <div className={styles.left}>
            <input
              className={styles.input}
              placeholder="Search name, email, or ID…"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(1); }}
            />
            <div className={styles.chips}>
              <button className={`${styles.chip} ${country === "" ? styles.active : ""}`} onClick={() => { setCountry(""); setPage(1); }}>All</button>
              {COUNTRIES.map(c => (
                <button key={c} className={`${styles.chip} ${country === c ? styles.active : ""}`} onClick={() => { setCountry(c); setPage(1); }}>
                  {c}
                </button>
              ))}
            </div>
          </div>
          <div className={styles.right}>
            <span className={styles.hint}>{status}{apiCount !== null ? ` • Total ${apiCount}` : ""}</span>
            <button className={styles.btn} onClick={fetchClients} disabled={loading}>↻ Refresh</button>
          </div>
        </div>

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th style={{width: '28%'}}>Name</th>
                <th style={{width: '30%'}}>Email</th>
                <th style={{width: '10%'}}>Country</th>
                <th style={{width: '16%'}}>National ID</th>
                <th style={{width: '16%'}}>Created</th>
              </tr>
            </thead>
            <tbody>
              {loading && [...Array(5)].map((_, i) => (
                <tr key={`sk-${i}`} className={styles.skelRow}><td colSpan={5}>&nbsp;</td></tr>
              ))}
              {!loading && pageItems.map((r, i) => (
                <tr key={i}>
                  <td className={styles.strong}>{[r.firstName, r.lastName].filter(Boolean).join(" ") || "-"}</td>
                  <td className={styles.truncate} title={r.email}>{r.email || "-"}</td>
                  <td><span className={`${styles.badge} ${styles[`badge${r.country || ""}`]}`}>{r.country || "-"}</span></td>
                  <td><code className={styles.mono}>{r.nationalId || "-"}</code></td>
                  <td>{fmtDate(r.createdAt)}</td>
                </tr>
              ))}
              {!loading && pageItems.length === 0 && (
                <tr><td colSpan={5} className={styles.empty}>No clients found.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className={styles.footer}>
          <div className={styles.hint}>
            Showing {(page - 1) * pageSize + (filtered.length ? 1 : 0)}–{Math.min(page * pageSize, filtered.length)} of {filtered.length}
            {apiCount !== null && filtered.length !== apiCount ? ` (API reported ${apiCount})` : ""}.
          </div>
          <div className={styles.pager}>
            <button className={styles.btn} disabled={page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}>Prev</button>
            <strong>{page}</strong>
            <span className={styles.hint}>/ {totalPages}</span>
            <button className={styles.btn} disabled={page >= totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))}>Next</button>
          </div>
        </div>
      </div>
    </div>
  );
}
