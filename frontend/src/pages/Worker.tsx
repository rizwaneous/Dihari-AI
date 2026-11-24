import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { BigButton, ErrorRetry, MicInput, pct, ScreenHeader, Skeleton, SpeakerButton, Stepper, useAsync } from "../components/ui";
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
    <div className="pb-8">
      <ScreenHeader title={t("ui.counter.title")} speakText={t("ui.counter.speak")} auto />
      <div className="p-4 space-y-6">
        <p className="text-xl">{j.task_icon} {j.task_name} · {j.location_text} · <b>{country?.currency.symbol} {j.daily_rate}</b></p>
        <Stepper value={val} onChange={setRate} min={min} max={max} step={step} unit={country?.currency.symbol} />
        <p className="text-lg text-center text-gray-700">{t("ui.counter.hint", { min: j.daily_rate })}</p>
        <MicInput onText={spoken} />
        {err && <ErrorRetry error={err} onRetry={() => setErr(null)} />}
        <BigButton icon="✔" onClick={send}>{t("ui.counter.send")}</BigButton>
        <BigButton tone="gray" onClick={() => nav("/")}>{t("ui.back")}</BigButton>
      </div>
    </div>
  );
}

export function MyWork() {
  const { t } = useI18n();
  const { country } = useSession();
  const { data, error, loading, reload } = useAsync(() => api<any[]>("/my/work"), [], true);
  const [err, setErr] = useState<unknown>(null);
  const [msg, setMsg] = useState<Record<string, string>>({});
  const sym = country?.currency.symbol || "";
  const act = async (id: string, path: string, body?: any, ok?: string) => {
    setErr(null);
    try { await api(path, { method: "POST", body: body ?? {}, retries: 1 }); if (ok) setMsg((m) => ({ ...m, [id]: ok })); await reload(); }
    catch (e) { if ((e as ApiError).code === "not_due_yet") setMsg((m) => ({ ...m, [id]: t("ui.pay.not_due", { day: data?.find((d) => d.assignment_id === id)?.payment_day }) })); else setErr(e); }
  };
  return (
    <div className="pb-28">
      <ScreenHeader title={t("ui.work.title")} speakText={t("ui.work.title")} />
      {loading && <Skeleton />}
      {!!error && <ErrorRetry error={error} onRetry={reload} />}
      {!!err && <ErrorRetry error={err} onRetry={() => setErr(null)} />}
      {data && !data.length && <p className="p-6 text-xl text-center">{t("ui.work.empty")}</p>}
      <div className="p-4 space-y-5">
        {data?.map((w) => (
          <article key={w.assignment_id} className="rounded-3xl border-4 border-gray-700 p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-2xl font-bold">{w.job.task_icon} {w.job.task_name} · {sym} {w.terms.daily_rate}</div>
              <SpeakerButton auto={w.status === "assigned"} text={w.status === "assigned" ? w.agreement_id : undefined} load={async () => (await api<{ text: string }>(`/agreements/${w.agreement_id}/readback`)).text} />
            </div>
            <p className="text-xl font-bold">{t(`ui.work.status.${w.status}`)}</p>
            {w.status === "assigned" && (<><AgreementBlock id={w.agreement_id} /><BigButton icon="✔" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/confirm`)}>{t("ui.work.confirm")}</BigButton>
              <BigButton tone="gray" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/cancel`)}>{t("ui.work.cancel")}</BigButton></>)}
            {w.status === "confirmed" && <><AgreementBlock id={w.agreement_id} />
              {w.job_status === "assigned" && <BigButton tone="gray" onClick={() => act(w.assignment_id, "/assignments/"+w.assignment_id+"/cancel")}>{t("ui.work.cancel")}</BigButton>}</>}
            {w.status === "completed" && !w.payment_report && (
              <div className="space-y-3"><div className="flex items-center justify-between"><p className="text-2xl font-bold">{t("ui.pay.q")}</p><SpeakerButton text={t("ui.pay.speak")} /></div>
                <BigButton tone="green" icon="💰" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/payment`, { status: "paid" }, t("ui.pay.thanks"))}>{t("ui.paid")}</BigButton>
                <BigButton tone="red" icon="🚫" onClick={() => act(w.assignment_id, `/assignments/${w.assignment_id}/payment`, { status: "unpaid" }, t("ui.pay.case"))}>{t("ui.notpaid")}</BigButton></div>)}
            {w.payment_report && <p className="p-3 rounded-2xl bg-gray-100 text-lg font-bold">{w.payment_report === "paid" ? t("ui.pay.thanks") : t("ui.pay.case")}</p>}
            {msg[w.assignment_id] && <p role="status" className="p-3 rounded-2xl bg-yellow-100 text-lg font-bold">{msg[w.assignment_id]}</p>}
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
    <div className="rounded-2xl bg-green-50 border-2 border-green-700 p-3 text-lg space-y-1">
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
    <div className="pb-28">
      <ScreenHeader title={t("ui.me.title")} speakText={t("ui.me.title")} />
      <div className="p-4 space-y-4">
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
