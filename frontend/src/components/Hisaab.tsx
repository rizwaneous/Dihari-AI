import { useEffect, useState } from "react";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { speak } from "../voice";
import { BigButton, errMsg, SpeakerButton, useAsync } from "./ui";

type Entry = { id: string; kind: string; amount: number; method: string | null; reference: string | null; note: string | null; by: string; confirmed: boolean; proof: boolean; at: string };
export type HisaabData = { assignment_id: string; daily_rate: number; days_worked: number; days_agreed: number | null; earned: number; received: number; deductions: number;
  agreed_deductions: number; cancellation_fees: number; pending_confirmation: number; balance: number; currency: string; speak: string; entries: Entry[] };

const KIND_ICON: Record<string, string> = { advance: "💵", kharchi: "🍞", payment: "💰", deduction: "➖", cancellation_fee: "⏰" };
const METHODS = ["cash", "jazzcash", "easypaisa", "bank"];

/** The running account for one job, readable by both sides: earned, received, still owed, each entry with its proof. */
export function Hisaab({ assignmentId, viewer, autoSpeak }: { assignmentId: string; viewer: "worker" | "hirer"; autoSpeak?: boolean }) {
  const { t, bcp47, lang } = useI18n();
  const { country } = useSession();
  const sym = country?.currency.symbol || "";
  const h = useAsync(() => api<HisaabData>(`/assignments/${assignmentId}/hisaab`), [assignmentId]);
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState(viewer === "worker" ? "payment" : "payment");
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cash");
  const [ref, setRef] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const d = h.data;
  useEffect(() => { if (autoSpeak && d) speak(d.speak, bcp47, lang); /* eslint-disable-next-line */ }, [autoSpeak, !!d]);
  if (!d) return h.loading ? <div className="skeleton h-24" /> : null;
  const m = (n: number) => `${sym} ${n.toLocaleString("en-US")}`;
  const kinds = viewer === "worker" ? ["payment", "advance", "kharchi"] : ["payment", "advance", "kharchi", "deduction"];
  const save = async () => {
    setErr(""); setBusy(true);
    try {
      const next = await api<HisaabData>(`/assignments/${assignmentId}/hisaab`, { method: "POST", retries: 0,
        body: { kind, amount: Number(amount), method, reference: method !== "cash" ? ref || null : null } });
      h.setData(next); setAdding(false); setAmount(""); setRef("");
    } catch (e) { setErr(errMsg(t, e)); }
    finally { setBusy(false); }
  };
  const confirm = async (id: string) => { try { h.setData(await api<HisaabData>(`/hisaab/${id}/confirm`, { method: "POST", retries: 0 })); } catch { setErr(t("ui.error.generic")); } };
  return <section className="card soft" aria-label={t("hs.title")}>
    <div className="card-row"><h2 className="grow">📒 {t("hs.title")}</h2><SpeakerButton text={d.speak} /></div>
    <div className="ledger-sum">
      <div><small>{t("hs.earned", { n: d.days_worked })}</small><b>{m(d.earned)}</b></div>
      <div><small>{t("hs.received")}</small><b>{m(d.received)}</b></div>
      <div className="bal"><small>{t(d.balance >= 0 ? "hs.balance" : "hs.over")}</small><b>{m(Math.abs(d.balance))}</b></div>
    </div>
    {(d.deductions + d.agreed_deductions) > 0 && <p className="muted">{t("hs.deducted", { amount: m(d.deductions + d.agreed_deductions) })}</p>}
    {d.cancellation_fees > 0 && <p className="status-line ok">⏰ {t("hs.fee", { amount: m(d.cancellation_fees) })}</p>}
    {d.pending_confirmation > 0 && <p className="status-line">{t(viewer === "worker" ? "hs.pending_worker" : "hs.pending_hirer", { amount: m(d.pending_confirmation) })}</p>}
    <div>{d.entries.map((e) => <div key={e.id} className="ledger-row">
      <span className="ico" aria-hidden="true">{KIND_ICON[e.kind] || "•"}</span>
      <div className="grow"><strong>{t("hs.kind." + e.kind)} · <span className="money">{m(e.amount)}</span></strong>
        <small>{new Date(e.at).toLocaleDateString(bcp47, { day: "numeric", month: "short" })} · {e.method ? t("hs.method." + e.method) : ""}{e.reference ? " · #" + e.reference : ""} · {t("hs.by." + e.by)}</small></div>
      {e.confirmed ? <small className={e.proof ? "proof-ok" : "muted"}>{e.proof ? "✔ " + t("hs.proof") : "✓"}</small>
        : viewer === "worker" && e.by === "hirer" ? <BigButton small tone="green" onClick={() => confirm(e.id)}>{t("hs.yes_got")}</BigButton>
        : <small className="proof-wait">⏳ {t("hs.waiting")}</small>}
    </div>)}</div>
    {adding ? <div className="card">
      <div className="chips-row" role="group">{kinds.map((k) => <button key={k} className={"chip" + (k === kind ? " on" : "")} onClick={() => setKind(k)}>{KIND_ICON[k]} {t("hs.kind." + k)}</button>)}</div>
      <label className="field">{t("hs.amount")} ({sym})<input inputMode="numeric" type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
      {kind !== "deduction" && <div className="chips-row" role="group">{METHODS.map((x) => <button key={x} className={"chip" + (x === method ? " on" : "")} onClick={() => setMethod(x)}>{t("hs.method." + x)}</button>)}</div>}
      {kind !== "deduction" && method !== "cash" && <label className="field">{t("hs.ref")}<input dir="ltr" maxLength={40} value={ref} onChange={(e) => setRef(e.target.value)} /></label>}
      {viewer === "hirer" && <small className="muted">{t("hs.hirer_note")}</small>}
      {err && <p className="status-line bad" role="alert">{err}</p>}
      <div className="btn-row"><BigButton disabled={busy || !(Number(amount) > 0)} onClick={save}>{t("hs.save")}</BigButton><BigButton tone="gray" onClick={() => setAdding(false)}>{t("ui.back")}</BigButton></div>
    </div> : <BigButton small tone="gray" icon="➕" onClick={() => setAdding(true)}>{t(viewer === "worker" ? "hs.add_worker" : "hs.add_hirer")}</BigButton>}
    {!adding && err && <p className="status-line bad" role="alert">{err}</p>}
  </section>;
}

/** Day-by-day presence for one job. */
export function AttendanceStrip({ assignmentId, version = 0 }: { assignmentId: string; version?: number }) {
  const { t, bcp47 } = useI18n();
  const a = useAsync(() => api<{ day: string; in: string | null; out: string | null; far: boolean; marked_by: string }[]>(`/assignments/${assignmentId}/attendance`), [assignmentId, version]);
  if (!a.data?.length) return null;
  return <div className="days-strip" aria-label={t("att.title")}>{a.data.map((r) => <span key={r.day} className={r.far ? "far" : r.in ? "in" : ""}
    title={r.far ? t("att.far") : ""}>{new Date(r.day + "T12:00").toLocaleDateString(bcp47, { day: "numeric", month: "short" })}{r.out ? " ✓" : r.in ? " •" : ""}</span>)}</div>;
}
