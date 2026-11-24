import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { BigButton, errMsg, ErrorRetry, pct, ScreenHeader, Skeleton, SpeakerButton, useAsync } from "../components/ui";
import { useI18n } from "../i18n";
import { TierBadge } from "../components/Tier";
import { TradeIcon } from "../components/TradeIcon";
import { AttendanceStrip, Hisaab } from "../components/Hisaab";
import { useSession } from "../session";

export function MyJobs() {
  const { t, bcp47 } = useI18n();
  const { country } = useSession();
  const { data, error, loading, reload } = useAsync(() => api<any[]>("/jobs/mine"), [], true);
  const live = data?.filter((j) => ["open", "offers", "assigned", "in_progress"].includes(j.status) && !(j.booking_expired && !j.booked)) || [];
  const past = data?.filter((j) => !live.includes(j)) || [];
  const row = (j: any) => (
    <Link key={j.id} to={`/jobs-mine/${j.id}`} className={"card" + (j.urgent ? " urgent" : "")}>
      <div className="card-row"><span className="trade-tile"><TradeIcon code={j.task} /></span>
        <div className="grow"><strong className="text-xl">{j.task_name}</strong><div className="muted">{j.location_text} · {new Date(j.start_at).toLocaleString(bcp47, { weekday: "short", hour: "numeric" })}</div></div>
        <b className="money text-xl">{country?.currency.symbol} {j.daily_rate}</b></div>
      <div className="card-row"><span className="pill">{t("map.booked", { n: j.booked, total: j.headcount })}</span>
        <span className="pill gray">{j.booking_expired && !j.booked ? t("map.expired") : t(`ui.status.${j.status}`)}</span>
        {j.urgent && <span className="pill urgent-badge">⚡ {t("urgent.badge")}</span>}
        {j.offer_count > 0 && j.status !== "assigned" && <span className="pill gold">🔔 {t("ui.myjobs.offers", { n: j.offer_count })}</span>}</div>
    </Link>);
  return (
    <div className="page">
      <ScreenHeader title={t("ui.myjobs.title")} speakText={live.length ? t("myjobs.speak", { n: live.length }) : t("ui.myjobs.empty")} />
      <div className="page-body">
        {loading && !data && <Skeleton />}
        {!!error && <ErrorRetry error={error} onRetry={reload} />}
        <Link to="/" className="btn btn-gold"><span className="ico" aria-hidden>➕</span>{t("map.request")}</Link>
        {data && !data.length && <div className="empty-state"><span className="art">📋</span><p className="text-xl">{t("ui.myjobs.empty")}</p></div>}
        {live.map(row)}
        {past.length > 0 && <h2 className="section-title muted">{t("myjobs.past")}</h2>}
        {past.map(row)}
      </div>
    </div>
  );
}

const SORTS = ["best", "distance", "price", "rating"];

export function JobDetail() {
  const { id } = useParams();
  const { t, lang } = useI18n();
  const { country } = useSession();
  const [sort, setSort] = useState("best");
  const [actErr, setActErr] = useState<unknown>(null);
  const [note, setNote] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [att, setAtt] = useState(0);
  const job = useAsync(() => api<any>(`/jobs/${id}`), [id], true);
  const offers = useAsync(() => api<any[]>(`/jobs/${id}/offers?sort=${sort}`), [id, sort], true);
  const asg = useAsync(() => api<any[]>(`/jobs/${id}/assignments`), [id], true);
  const j = job.data;
  const sym = country?.currency.symbol || "";
  const reloadAll = () => Promise.all([job.reload(true), offers.reload(true), asg.reload(true)]);
  const act = async (path: string, body: any = {}, ok?: string) => {
    setActErr(null); setNote("");
    try { const r = await api<any>(path, { method: "POST", body, retries: 0 }); if (ok) setNote(ok); await reloadAll(); return r; } catch (e) { setActErr(e); }
  };
  if (job.loading && !j) return <Skeleton />;
  if (job.error) return <ErrorRetry error={job.error} onRetry={job.reload} />;
  const open_ = ["open", "offers", "assigned"].includes(j.status);
  const active = ["assigned", "in_progress"].includes(j.status);
  const confirmed = asg.data?.filter((a) => a.status === "confirmed").length || 0;
  const spots = j.headcount - j.booked;
  const tradeName = (c: string) => country?.trades.find((x) => x.code === c)?.names[lang] || c;
  return (
    <div className="page">
      <ScreenHeader back="/jobs-mine" title={j.task_name} speakText={`${j.task_name} ${j.location_text}. ${t("ui.job.rate", { rate: j.daily_rate })}. ${j.booking_expired && !j.booked ? t("map.expired") : t(`ui.status.${j.status}`)}`} />
      <div className="page-body">
        <div className={"card" + (j.urgent ? " urgent" : "")}>
          <div className="card-row"><span className="trade-tile"><TradeIcon code={j.task} size={44} /></span>
            <div className="grow"><strong className="text-xl">{j.location_text}</strong><div className="muted">{t("ui.job.workers", { n: j.headcount })} · {t("map.booked", { n: j.booked, total: j.headcount })}</div></div>
            <b className="big-num">{sym} {j.daily_rate}</b></div>
          <div className="card-row"><span className="pill">{j.booking_expired && !j.booked ? t("map.expired") : t(`ui.status.${j.status}`)}</span>{j.urgent && <span className="pill urgent-badge">⚡ {t("urgent.badge")}</span>}</div>
        </div>
        {!!actErr && <p role="alert" className="status-line bad">{errMsg(t, actErr)}</p>}
        {note && <p role="status" className="status-line ok">{note}</p>}

        {open_ && !j.booking_expired && spots > 0 && <InviteFree job={j} onDone={reloadAll} />}
        {open_ && !j.booking_expired && spots > 0 && <BookTeam job={j} onDone={reloadAll} />}

        {open_ && !j.booking_expired && (
          <section className="grid gap-3">
            <h2 className="section-title">{t("ui.offers.title")}</h2>
            <div className="chips-row" role="group">{SORTS.map((s) => <button key={s} onClick={() => setSort(s)} className={"chip" + (s === sort ? " on" : "")}>{t(`ui.offers.sort.${s}`)}</button>)}</div>
            {offers.loading && !offers.data && <Skeleton n={2} />}
            {offers.data && !offers.data.length && <p className="muted">{t("ui.offers.none")}</p>}
            {offers.data?.map((o) => (
              <div key={o.offer_id} className="card">
                <div className="person"><span className="avatar" aria-hidden>👷</span>
                  <div className="grow"><strong>{o.first_name} <TierBadge tier={o.tier} /></strong>
                    <small className="muted">{o.distance_km != null && t("ui.job.km", { km: o.distance_km })} · {pct(o.completion_rate) ? t("ui.offers.completion", { pct: pct(o.completion_rate)! }) : t("ui.offers.new_worker")}{o.avg_rating ? ` · ★ ${o.avg_rating.toFixed(1)}` : ""}</small></div>
                  <b className="money text-xl">{sym} {o.rate}</b></div>
                {o.skills?.length > 0 && <div className="skill-list">{o.skills.map((s: any) => <span key={s.trade} className="skill"><TradeIcon code={s.trade} />{tradeName(s.trade)} ×{s.endorsements}</span>)}</div>}
                {o.kind === "counter" && <p className="status-line">↑ {t("ui.offers.counter", { rate: o.rate })}</p>}
                <BigButton tone={o.status === "selected" ? "gray" : "green"} disabled={o.status === "selected"} icon="👆" onClick={() => act(`/jobs/${id}/assign`, { offer_ids: [o.offer_id] })}>{o.status === "selected" ? t("ui.offers.picked") : t("ui.offers.pick")}</BigButton>
              </div>))}
          </section>)}

        {asg.data && asg.data.length > 0 && (
          <section className="grid gap-3">
            <h2 className="section-title">{t("job.crew")}</h2>
            {asg.data.map((a) => (
              <div key={a.assignment_id} className="card">
                <div className="person"><span className="avatar" aria-hidden>👷</span>
                  <div className="grow"><strong>{a.first_name} <TierBadge tier={a.tier} /></strong><small className="muted"><a dir="ltr" href={`tel:${a.phone}`}>{a.phone}</a> · {t(`ui.work.status.${a.status}`)}</small></div>
                  <a className="speaker" href={`tel:${a.phone}`} aria-label={t("market.call")}>📞</a></div>
                {active && a.status === "confirmed" && <>
                  <AttendanceStrip assignmentId={a.assignment_id} version={att} />
                  <BigButton small tone="gray" icon="✅" onClick={async () => { if (await act(`/assignments/${a.assignment_id}/check-in`, {}, t("att.marked", { name: a.first_name }))) setAtt((n) => n + 1); }}>{t("att.mark")}</BigButton></>}
                {(j.status === "completed" || j.status === "disputed") && a.status === "completed" && <>
                  {!a.my_payment_claim && <><p className="text-lg font-bold">{t("ui.hirer.paid_q")}</p>
                    <div className="btn-row"><BigButton tone="green" onClick={() => act(`/assignments/${a.assignment_id}/hirer-payment`, { status: "paid" })}>{t("ui.hirer.i_paid")}</BigButton>
                      <BigButton tone="gray" onClick={() => act(`/assignments/${a.assignment_id}/hirer-payment`, { status: "not_yet" })}>{t("ui.hirer.not_yet")}</BigButton></div></>}
                  {!a.rating ? <><p className="font-bold">{t("job.rate_q", { name: a.first_name })}</p><div className="stars">{[1, 2, 3, 4, 5].map((s) => <button key={s} aria-label={`${s}`} onClick={() => act(`/assignments/${a.assignment_id}/rate`, { stars: s })}>⭐</button>)}</div></>
                    : <Endorse workerId={a.worker_id} trade={j.task} name={a.first_name} />}</>}
                {["confirmed", "completed"].includes(a.status) && (open[a.assignment_id]
                  ? <Hisaab assignmentId={a.assignment_id} viewer="hirer" />
                  : <BigButton small tone="gray" icon="📒" onClick={() => setOpen((o) => ({ ...o, [a.assignment_id]: true }))}>{t("hs.open")}</BigButton>)}
              </div>))}
            {j.status === "assigned" && (confirmed > 0
              ? <BigButton icon="▶" onClick={() => act(`/jobs/${id}/start`)}>{t("ui.hirer.start")}</BigButton>
              : <p className="status-line">{t("ui.hirer.waiting_confirm")}</p>)}
            {j.status === "in_progress" && <BigButton icon="🏁" onClick={() => act(`/jobs/${id}/complete`)}>{t("ui.hirer.complete")}</BigButton>}
          </section>)}

        {open_ && <CancelJob id={id!} onDone={(n) => { setNote(n ? t("job.cancel_fee", { n }) : t("job.cancelled")); reloadAll(); }} />}
        <CasesNotice />
      </div>
    </div>
  );
}

function CancelJob({ id, onDone }: { id: string; onDone: (feeWorkers: number) => void }) {
  const { t } = useI18n();
  const [ask, setAsk] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  if (!ask) return <BigButton small tone="gray" icon="✖" onClick={() => setAsk(true)}>{t("ui.hirer.cancel")}</BigButton>;
  return <div className="card warn"><p className="font-bold">{t("job.cancel_q")}</p><small>{t("job.cancel_rule")}</small>
    {!!err && <p className="status-line bad">{errMsg(t, err)}</p>}
    <div className="btn-row"><BigButton tone="red" onClick={async () => { try { const r = await api<any>(`/jobs/${id}/cancel`, { method: "POST", body: {}, retries: 0 }); setAsk(false); onDone(r?.late_fee_workers || 0); } catch (e) { setErr(e); } }}>{t("job.cancel_yes")}</BigButton>
      <BigButton tone="gray" onClick={() => setAsk(false)}>{t("ui.back")}</BigButton></div></div>;
}

/** After rating: vouch for the worker's skill in this trade (builds their skill badges). */
function Endorse({ workerId, trade, name }: { workerId: string; trade: string; name: string }) {
  const { t, lang } = useI18n();
  const { country } = useSession();
  const [done, setDone] = useState(false);
  if (!workerId) return null;
  const tn = country?.trades.find((x) => x.code === trade)?.names[lang] || trade;
  if (done) return <p className="status-line ok">🏅 {t("skill.thanks", { name })}</p>;
  return <BigButton small tone="gold" icon="🏅" onClick={async () => { try { await api(`/workers/${workerId}/endorse`, { method: "POST", body: { trade }, retries: 0 }); setDone(true); } catch { /* already endorsed or not eligible */ setDone(true); } }}>{t("skill.endorse", { name, trade: tn })}</BigButton>;
}

/** Workers who said "free today" near this job: invite them directly. */
function InviteFree({ job, onDone }: { job: any; onDone: () => void }) {
  const { t } = useI18n();
  const [show, setShow] = useState(false);
  const [sent, setSent] = useState<Record<string, boolean>>({});
  const list = useAsync(() => show && job.lat != null ? api<any[]>(`/workers/available?lat=${job.lat}&lon=${job.lon}&trade=${job.task}`) : Promise.resolve([]), [show, job.id]);
  if (!show) return <BigButton small tone="blue" icon="📣" onClick={() => setShow(true)}>{t("free.invite_open")}</BigButton>;
  return <section className="card soft"><h2>📣 {t("free.near_job")}</h2>
    {list.loading && <div className="skeleton h-16" />}
    {list.data && !list.data.length && <p className="muted">{t("free.none")}</p>}
    {list.data?.map((w) => <div key={w.worker_id} className="person"><span className="avatar" aria-hidden>👷</span>
      <div className="grow"><strong>{w.first_name} <TierBadge tier={w.tier} /></strong><small className="muted">{t("ui.job.km", { km: w.distance_km })}</small></div>
      <BigButton small tone={sent[w.worker_id] ? "gray" : "green"} disabled={sent[w.worker_id]} className="!w-auto" onClick={async () => { try { await api(`/jobs/${job.id}/invite`, { method: "POST", body: { worker_id: w.worker_id }, retries: 0 }); } catch { /* already invited */ } setSent((s) => ({ ...s, [w.worker_id]: true })); onDone(); }}>{sent[w.worker_id] ? t("free.invited") : t("free.invite")}</BigButton></div>)}
  </section>;
}

/** Thekedar's own crew: put chosen members on this job in one tap. */
function BookTeam({ job, onDone }: { job: any; onDone: () => void }) {
  const { t } = useI18n();
  const teams = useAsync(() => api<any[]>("/teams"), []);
  const [pick, setPick] = useState<Record<string, boolean>>({});
  const [err, setErr] = useState<unknown>(null);
  const [show, setShow] = useState(false);
  const members = teams.data?.flatMap((tm) => tm.members) || [];
  if (!members.length) return null;
  if (!show) return <BigButton small tone="gray" icon="👥" onClick={() => setShow(true)}>{t("team.book_open")}</BigButton>;
  const chosen = Object.keys(pick).filter((k) => pick[k]);
  return <section className="card soft"><h2>👥 {t("team.book_title")}</h2>
    {members.map((m) => <label key={m.worker_id} className="person"><input type="checkbox" className="w-7 h-7" checked={!!pick[m.worker_id]} onChange={(e) => setPick((p) => ({ ...p, [m.worker_id]: e.target.checked }))} />
      <div className="grow"><strong>{m.name}</strong><small className="muted">{m.available ? "🟢 " + t("free.today") : ""}</small></div></label>)}
    {!!err && <p className="status-line bad">{errMsg(t, err)}</p>}
    <BigButton disabled={!chosen.length || chosen.length > job.headcount - job.booked} onClick={async () => { setErr(null); try { await api(`/jobs/${job.id}/book-team`, { method: "POST", body: { worker_ids: chosen }, retries: 0 }); setShow(false); setPick({}); onDone(); } catch (e) { setErr(e); } }}>{t("team.book", { n: chosen.length })}</BigButton>
  </section>;
}

function CasesNotice() {
  const { t } = useI18n();
  const { data } = useAsync(() => api<any[]>("/my/cases"));
  if (!data?.length) return null;
  return <div className="card warn"><p className="text-xl font-bold">⚠️ {t("ui.case.title")}</p><p>{t("ui.case.body")}</p></div>;
}

export { SpeakerButton };
