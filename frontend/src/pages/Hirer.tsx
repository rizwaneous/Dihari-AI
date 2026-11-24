import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { BigButton, ErrorRetry, pct, ScreenHeader, Skeleton, SpeakerButton, useAsync } from "../components/ui";
import { useI18n } from "../i18n";
import { useSession } from "../session";

export function MyJobs() {
  const { t, bcp47 } = useI18n();
  const { country } = useSession();
  const { data, error, loading, reload } = useAsync(() => api<any[]>("/jobs/mine"));
  return (
    <div className="pb-28">
      <ScreenHeader title={t("ui.myjobs.title")} speakText={t("ui.myjobs.title")} />
      {loading && <Skeleton />}
      {!!error && <ErrorRetry error={error} onRetry={reload} />}
      {data && !data.length && <p className="p-6 text-xl text-center">{t("ui.myjobs.empty")}</p>}
      <div className="p-4 space-y-4">
        {data?.map((j) => (
          <Link key={j.id} to={`/jobs-mine/${j.id}`} className="block rounded-2xl border-4 border-gray-600 p-4 space-y-1 min-h-[96px]">
            <div className="flex justify-between text-2xl font-bold"><span><span aria-hidden>{j.task_icon}</span> {j.task_name} · {j.location_text}</span><span>{country?.currency.symbol} {j.daily_rate}</span></div>
            <div className="flex justify-between text-lg"><span>{new Date(j.start_at).toLocaleString(bcp47, { weekday: "short", hour: "numeric" })} · {t("map.booked", { n:j.booked, total:j.headcount })}</span>
              <span className="font-bold">{j.booking_expired && !j.booked ? t("map.expired") : t(`ui.status.${j.status}`)}</span></div>
            {j.offer_count > 0 && j.status !== "assigned" && <p className="text-lg font-bold text-green-800">🔔 {t("ui.myjobs.offers", { n: j.offer_count })}</p>}
          </Link>))}
      </div>
    </div>
  );
}

const SORTS = ["best", "distance", "price", "rating"];

export function JobDetail() {
  const { id } = useParams();
  const { t, lang } = useI18n();
  const { country } = useSession();
  const nav = useNavigate();
  const [sort, setSort] = useState("best");
  const [actErr, setActErr] = useState<unknown>(null);
  const job = useAsync(() => api<any>(`/jobs/${id}`), [id], true);
  const offers = useAsync(() => api<any[]>(`/jobs/${id}/offers?sort=${sort}`), [id, sort], true);
  const asg = useAsync(() => api<any[]>(`/jobs/${id}/assignments`), [id], true);
  const j = job.data;
  const sym = country?.currency.symbol || "";
  const act = async (path: string, body: any = {}) => {
    setActErr(null);
    try { await api(path, { method: "POST", body, retries: 0 }); await Promise.all([job.reload(), offers.reload(), asg.reload()]); } catch (e) { setActErr(e); }
  };
  if (job.loading && !j) return <Skeleton />;
  if (job.error) return <ErrorRetry error={job.error} onRetry={job.reload} />;
  const open = j.status === "open" || j.status === "offers" || j.status === "assigned";
  const confirmed = asg.data?.filter((a) => a.status === "confirmed").length || 0;
  return (
    <div className="pb-28">
      <ScreenHeader title={`${j.task_icon} ${j.task_name}`} speakText={`${j.task_name} ${j.location_text}. ${t("ui.job.rate", { rate: j.daily_rate })}. ${j.booking_expired && !j.booked ? t("map.expired") : t(`ui.status.${j.status}`)}`} />
      <div className="p-4 space-y-4">
        <button className="underline text-lg min-h-[56px]" onClick={() => nav("/jobs-mine")}>← {t("ui.back")}</button>
        <div className="rounded-2xl bg-gray-100 p-4 text-xl font-bold space-y-1">
          <p>{j.location_text} · {sym} {j.daily_rate} · {t("ui.job.workers", { n: j.headcount })}</p>
          <p>{t("map.booked", {n:j.booked,total:j.headcount})}</p><p className="text-green-800">{j.booking_expired && !j.booked ? t("map.expired") : t(`ui.status.${j.status}`)}</p>
        </div>
        {!!actErr && <ErrorRetry error={actErr} onRetry={() => setActErr(null)} />}

        {open && !j.booking_expired && (j.status === "open" || j.status === "offers" || j.status === "assigned") && (
          <section className="space-y-3">
            <h2 className="text-2xl font-bold">{t("ui.offers.title")}</h2>
            <div className="flex gap-2 overflow-x-auto" role="group">{SORTS.map((s) => <button key={s} onClick={() => setSort(s)} className={`min-h-[56px] px-4 rounded-2xl font-bold text-lg border-4 whitespace-nowrap ${s === sort ? "bg-brand text-white border-brand" : "border-gray-500"}`}>{t(`ui.offers.sort.${s}`)}</button>)}</div>
            {offers.loading && <Skeleton n={2} />}
            {offers.data && !offers.data.length && <p className="text-xl">{t("ui.offers.none")}</p>}
            {offers.data?.map((o) => (
              <div key={o.offer_id} className="rounded-2xl border-4 border-gray-600 p-4 space-y-2">
                <div className="flex justify-between text-2xl font-bold"><span>👷 {o.first_name}</span><span>{sym} {o.rate}</span></div>
                {o.kind === "counter" && <p className="text-lg text-yellow-900 font-bold">↑ {t("ui.offers.counter", { rate: o.rate })}</p>}
                <p className="text-lg">{o.distance_km != null && t("ui.job.km", { km: o.distance_km })} · {pct(o.completion_rate) ? t("ui.offers.completion", { pct: pct(o.completion_rate)! }) : t("ui.offers.new_worker")}{o.avg_rating ? ` · ⭐ ${o.avg_rating.toFixed(1)}` : ""}</p>
                <BigButton tone={o.status === "selected" ? "gray" : "green"} disabled={o.status === "selected"} icon="👆" onClick={() => act(`/jobs/${id}/assign`, { offer_ids: [o.offer_id] })}>{o.status === "selected" ? t("ui.offers.picked") : t("ui.offers.pick")}</BigButton>
              </div>))}
          </section>)}

        {asg.data && asg.data.length > 0 && (
          <section className="space-y-3">
            {asg.data.map((a) => (
              <div key={a.assignment_id} className="rounded-2xl border-4 border-brand p-4 space-y-2">
                <p className="text-xl font-bold">👷 {a.first_name} · <span dir="ltr">{a.phone}</span> · {t(`ui.work.status.${a.status}`)}</p>
                {j.status === "completed" || j.status === "disputed" ? (
                  <>{a.status === "completed" && !a.my_payment_claim && (<><p className="text-lg font-bold">{t("ui.hirer.paid_q")}</p>
                    <div className="grid grid-cols-2 gap-3"><BigButton tone="green" onClick={() => act(`/assignments/${a.assignment_id}/hirer-payment`, { status: "paid" })}>{t("ui.hirer.i_paid")}</BigButton>
                      <BigButton tone="gray" onClick={() => act(`/assignments/${a.assignment_id}/hirer-payment`, { status: "not_yet" })}>{t("ui.hirer.not_yet")}</BigButton></div></>)}
                    {a.status === "completed" && !a.rating && <div className="flex gap-2 justify-center" dir="ltr">{[1, 2, 3, 4, 5].map((s) => <button key={s} aria-label={`${s}`} className="min-w-[56px] min-h-[56px] text-3xl rounded-xl border-2" onClick={() => act(`/assignments/${a.assignment_id}/rate`, { stars: s })}>⭐</button>)}</div>}</>) : null}
              </div>))}
            {j.status === "assigned" && (confirmed > 0
              ? <BigButton icon="▶" onClick={() => act(`/jobs/${id}/start`)}>{t("ui.hirer.start")}</BigButton>
              : <p className="text-lg font-bold text-center">{t("ui.hirer.waiting_confirm")}</p>)}
            {j.status === "in_progress" && <BigButton icon="🏁" onClick={() => act(`/jobs/${id}/complete`)}>{t("ui.hirer.complete")}</BigButton>}
          </section>)}

        {(j.status === "open" || j.status === "offers" || j.status === "assigned") && <BigButton tone="red" onClick={() => act(`/jobs/${id}/cancel`)}>{t("ui.hirer.cancel")}</BigButton>}
        <CasesNotice />
        <span className="hidden">{lang}</span>
      </div>
    </div>
  );
}

function CasesNotice() {
  const { t } = useI18n();
  const { data } = useAsync(() => api<any[]>("/my/cases"));
  if (!data?.length) return null;
  return <div className="p-4 rounded-2xl border-4 border-red-700 bg-red-50"><p className="text-xl font-bold">⚠️ {t("ui.case.title")}</p><p className="text-lg">{t("ui.case.body")}</p></div>;
}
