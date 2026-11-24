import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { BigButton, errMsg, ErrorRetry, MicInput, pct, ScreenHeader, Skeleton, SpeakerButton, Stepper, useAsync } from "../components/ui";
import { AttendanceStrip, Hisaab } from "../components/Hisaab";
import { TradeIcon } from "../components/TradeIcon";
import { here } from "../components/Shell";
import { speak } from "../voice";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { ProfileForm } from "./Onboarding";

export function ReportLink({ id }: { id: string }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return <button className="underline text-lg min-h-[56px]" disabled={done} onClick={async () => { try { await api("/reports", { method: "POST", body: { target_type: "job", target_id: id, reason: "reported" } }); setDone(true); } catch { /* ignore */ } }}>{done ? t("ui.report.sent") : `🚩 ${t("ui.report.job")}`}</button>;
}

export function Counter() {
  const { id } = useParams();
  const { t } = useI18n();
  const { country } = useSession();
  const nav = useNavigate();
  const job = useAsync(() => api<any>(`/jobs/${id}`), [id]);
  const [rate, setRate] = useState<number | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);
  const j = job.data;
  const step = country?.rate_step || 50;
  if (job.loading) return <Skeleton n={1} />;
  if (job.error || !j) return <ErrorRetry error={job.error} onRetry={job.reload} />;
  const min = j.daily_rate + step, max = Math.floor(j.daily_rate * (country?.max_counter_multiple || 2));
  const val = rate ?? min;
  const spoken = async (txt: string) => {
    const d = await api<any>("/voice/answer", { method: "POST", body: { field: "daily_rate", transcript: txt, fields: {} } });
    const v = d.fields?.daily_rate; if (v) setRate(Math.min(max, Math.max(min, v)));
  };
  const send = async () => { setErr(null); try { await api(`/jobs/${id}/offers`, { method: "POST", body: { rate: val }, retries: 1 }); nav("/"); } catch (e) { setErr(e as ApiError); } };
  return (
    <div className="page">
      <ScreenHeader title={t("ui.counter.title")} speakText={t("ui.counter.speak")} auto back="/" />
      <div className="page-body">
        <div className="card card-row"><span className="trade-tile"><TradeIcon code={j.task} /></span><div className="grow"><strong className="text-xl">{j.task_name}</strong><div className="muted">{j.location_text} · <span className="money">{country?.currency.symbol} {j.daily_rate}</span></div></div></div>
        <Stepper value={val} onChange={setRate} min={min} max={max} step={step} unit={country?.currency.symbol} />
        <p className="text-lg text-center muted">{t("ui.counter.hint", { min: j.daily_rate })}</p>
        <MicInput onText={spoken} />
        {err && <ErrorRetry error={err} onRetry={() => setErr(null)} />}
        <BigButton icon="✔" onClick={send}>{t("ui.counter.send")}</BigButton>
        <BigButton tone="gray" onClick={() => nav("/")}>{t("ui.back")}</BigButton>
      </div>
    </div>
  );
}

export function MyWork() {
  const { t, bcp47, lang } = useI18n();
  const { country } = useSession();
  const [params, setParams] = useSearchParams();
  const { data, error, loading, reload } = useAsync(() => api<any[]>("/my/work"), [], true);
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<Record<string, { text: string; tone?: "ok" | "bad" }>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [att, setAtt] = useState(0);
  const [busy, setBusy] = useState("");
  const sym = country?.currency.symbol || "";
  const note = (id: string, text: string, tone?: "ok" | "bad") => { setMsg((m) => ({ ...m, [id]: { text, tone } })); speak(text, bcp47, lang); };
  const act = async (id: string, path: string, body?: any, ok?: string) => {
    setErr(null);
    try { await api(path, { method: "POST", body: body ?? {}, retries: 1 }); if (ok) note(id, ok, "ok"); await reload(); }
    catch (e) { if ((e as ApiError).code === "not_due_yet") note(id, t("ui.pay.not_due", { day: data?.find((d) => d.assignment_id === id)?.payment_day })); else setErr(e); }
  };
  const checkIn = async (id: string) => {
    setBusy(id); const p = await here();
    try { const r = await api<{ far: boolean; distance_m: number | null }>(`/assignments/${id}/check-in`, { method: "POST", body: p || {}, retries: 0 });
      note(id, r.far ? t("att.in_far", { m: r.distance_m || 0 }) : t("att.in_ok"), r.far ? undefined : "ok"); setAtt((n) => n + 1); }
    catch (e) { note(id, errMsg(t, e), "bad"); } finally { setBusy(""); }
  };
  const checkOut = async (id: string) => {
    setBusy(id);
    try { await api(`/assignments/${id}/check-out`, { method: "POST", body: {}, retries: 0 }); note(id, t("att.out_ok"), "ok"); setAtt((n) => n + 1); }
    catch (e) { note(id, errMsg(t, e), "bad"); } finally { setBusy(""); }
  };
  const active = (w: any) => w.status === "confirmed" && ["assigned", "in_progress"].includes(w.job_status);
  // Voice shortcuts: /work?do=check_in | check_out | hisaab act on the current job.
  const todo = params.get("do");
  useEffect(() => {
    if (!todo || !data) return;
    const cur = data.find(active) || data.find((w) => w.status === "completed");
    setParams({}, { replace: true });
    if (!cur) { speak(t("ui.work.empty"), bcp47, lang); return; }
    if (todo === "check_in") checkIn(cur.assignment_id);
    else if (todo === "check_out") checkOut(cur.assignment_id);
    else if (todo === "hisaab") setOpen((o) => ({ ...o, [cur.assignment_id]: true }));
    /* eslint-disable-next-line */ }, [todo, data]);
  const sorted = data ? [...data].sort((a, b) => Number(active(b)) - Number(active(a))) : null;
  return (
    <div className="page">
      <ScreenHeader title={t("ui.work.title")} speakText={data?.length ? t("work.speak", { n: data.length }) : t("ui.work.empty")} />
      <div className="page-body">
      {loading && !data && <Skeleton />}
      {!!error && <ErrorRetry error={error} onRetry={reload} />}
      {!!err && <ErrorRetry error={err} onRetry={() => setErr(null)} />}
      {data && !data.length && <div className="empty-state"><span className="art">🧭</span><p className="text-xl">{t("ui.work.empty")}</p><Link className="btn btn-green" to="/">{t("work.find")}</Link></div>}
        {sorted?.map((w) => (
          <article key={w.assignment_id} className={"card" + (active(w) ? " gold" : "")}>
            <div className="card-row">
              <span className="trade-tile"><TradeIcon code={w.job.task} /></span>
              <div className="grow"><strong className="text-xl">{w.job.task_name}</strong><div className="muted">{w.job.location_text} · <span className="money">{sym} {w.terms.daily_rate}</span></div></div>
              <SpeakerButton auto={w.status === "assigned"} load={async () => (await api<{ text: string }>(`/agreements/${w.agreement_id}/readback`)).text} />
            </div>
            <div><span className={"pill " + (w.status === "cancelled" || w.status === "no_show" ? "red" : w.status === "completed" ? "gray" : "")}>{t(`ui.work.status.${w.status}`)}</span>
              {w.job.urgent && <span className="pill urgent-badge" style={{ marginInlineStart: 6 }}>⚡ {t("urgent.badge")}</span>}</div>
            {w.status === "assigned" && (<><AgreementBlock id={w.agreement_id} /><BigButton icon="✔" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/confirm`)}>{t("ui.work.confirm")}</BigButton>
              <BigButton tone="gray" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/cancel`)}>{t("ui.work.cancel")}</BigButton></>)}
            {w.status === "confirmed" && <AgreementBlock id={w.agreement_id} />}
            {active(w) && <>
              <div className="btn-row">
                <BigButton className="check-big" icon="📍" disabled={busy === w.assignment_id} onClick={() => checkIn(w.assignment_id)}>{t("att.in")}</BigButton>
                <BigButton className="check-big" tone="blue" icon="🏁" disabled={busy === w.assignment_id} onClick={() => checkOut(w.assignment_id)}>{t("att.out")}</BigButton>
              </div>
              <AttendanceStrip assignmentId={w.assignment_id} version={att} />
              {w.job_status === "assigned" && <BigButton small tone="gray" onClick={() => act(w.assignment_id, "/assignments/" + w.assignment_id + "/cancel")}>{t("ui.work.cancel")}</BigButton>}
            </>}
            {w.status === "completed" && !w.payment_report && (
              <div className="card soft"><div className="card-row"><p className="text-xl font-bold grow">{t("ui.pay.q")}</p><SpeakerButton text={t("ui.pay.speak")} auto /></div>
                <div className="btn-row"><BigButton tone="green" icon="💰" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/payment`, { status: "paid" }, t("ui.pay.thanks"))}>{t("ui.paid")}</BigButton>
                <BigButton tone="red" icon="🚫" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/payment`, { status: "unpaid" }, t("ui.pay.case"))}>{t("ui.notpaid")}</BigButton></div></div>)}
            {w.payment_report && <p className={"status-line " + (w.payment_report === "paid" ? "ok" : "bad")}>{w.payment_report === "paid" ? t("ui.pay.thanks") : t("ui.pay.case")}</p>}
            {msg[w.assignment_id] && <p role="status" className={"status-line " + (msg[w.assignment_id].tone || "")}>{msg[w.assignment_id].text}</p>}
            {["confirmed", "completed"].includes(w.status) && (open[w.assignment_id]
              ? <Hisaab assignmentId={w.assignment_id} viewer="worker" autoSpeak />
              : <BigButton small tone="gray" icon="📒" onClick={() => setOpen((o) => ({ ...o, [w.assignment_id]: true }))}>{t("hs.open")}</BigButton>)}
          </article>))}
      </div>
    </div>
  );
}

function AgreementBlock({ id }: { id: string }) {
  const { t } = useI18n();
  const { data } = useAsync(() => api<any>(`/agreements/${id}`), [id]);
  if (!data) return null;
  return (
    <div className="card soft">
      <p className="font-bold">{t("ui.work.terms")} <span className="text-sm text-gray-600" dir="ltr">#{data.terms_hash.slice(0, 8)}</span></p>
      {data.terms.address_detail && <p>{t("ui.work.location_exact", { addr: data.terms.address_detail })}</p>}
      {data.terms.lat != null && <a className="text-button" target="_blank" rel="noreferrer" href={"https://www.google.com/maps/dir/?api=1&destination="+data.terms.lat+","+data.terms.lon}>{t("map.directions")}</a>}
      {data.hirer && <p>{data.hirer.first_name} · <a className="underline" dir="ltr" href={`tel:${data.hirer.phone}`}>{data.hirer.phone}</a></p>}
    </div>
  );
}

export function Me() {
  const { t } = useI18n();
  const { me, logout } = useSession();
  const rep = useAsync(() => api<any>(`/reputation/${me!.id}`));
  const [edit, setEdit] = useState(false);
  if (edit) return <ProfileForm onSaved={() => setEdit(false)} />;
  return (
    <div className="page">
      <ScreenHeader title={t("ui.me.title")} speakText={t("ui.me.title")} />
      <div className="page-body">
        <p className="text-3xl font-bold">👤 {me?.name || me?.id.slice(0, 6)}</p>
        {rep.data && <div className="rounded-2xl bg-gray-100 p-4 text-xl font-bold space-y-1">
          {pct(rep.data.completion_rate) && <p>{t("ui.me.on_time", { pct: pct(rep.data.completion_rate)! })}</p>}
          {rep.data.avg_rating && <p>{t("ui.me.rating", { r: rep.data.avg_rating.toFixed(1) })}</p>}</div>}
        <BigButton tone="blue" icon="✏️" onClick={() => setEdit(true)}>{t("ui.setup.area")}</BigButton>
        <BigButton tone="gray" onClick={logout}>{t("ui.me.logout")}</BigButton>
      </div>
    </div>
  );
}
