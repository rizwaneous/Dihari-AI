import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, getToken } from "../api";
import { BigButton, errMsg, ErrorRetry, ScreenHeader, Skeleton, SpeakerButton, autoVoiceOn, setAutoVoice, useAsync } from "../components/ui";
import { TierBadge, type Tier } from "../components/Tier";
import { TradeIcon } from "../components/TradeIcon";
import { here, useBus } from "../components/Shell";
import type { WorkLocation } from "../components/useWorkLocation";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { speak } from "../voice";

/* ============================== worker: "free today" switch ============================== */
export function FreeToggle() {
  const { t, bcp47, lang } = useI18n();
  const { me, refresh } = useSession();
  const [on, setOn] = useState<boolean>(!!(me as any)?.available_today);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setOn(!!(me as any)?.available_today); }, [me]);
  useBus("available", useCallback(() => { setOn(true); refresh(); }, [refresh]));
  const flip = async () => {
    setBusy(true);
    const p = !on ? await here(4000) : null;
    try { await api("/me/available", { method: "POST", body: { available: !on, ...(p || {}) }, retries: 0 }); setOn(!on); speak(t(!on ? "free.on_said" : "free.off_said"), bcp47, lang); }
    catch { /* stays as it was */ } finally { setBusy(false); }
  };
  return <button className={"free-toggle" + (on ? " on" : "")} onClick={flip} disabled={busy} aria-pressed={on}>
    <span className="knob"><i /></span>
    <span className="grow"><strong>{t(on ? "free.on" : "free.off")}</strong><small>{t(on ? "free.on_hint" : "free.off_hint")}</small></span>
  </button>;
}

/* ============================== worker: invites from hirers ============================== */
export function Invites({ onOpen }: { onOpen: (jobId: string) => void }) {
  const { t } = useI18n();
  const { country } = useSession();
  const inv = useAsync(() => api<{ invite_id: string; job: any }[]>("/my/invites"), [], true);
  if (!inv.data?.length) return null;
  const sym = country?.currency.symbol || "";
  return <div className="grid gap-2">{inv.data.map(({ invite_id, job }) => <div key={invite_id} className="card invite-card">
    <div className="card-row"><span className="trade-tile"><TradeIcon code={job.task} /></span>
      <div className="grow"><small className="muted">📣 {t("inv.title")}</small><strong className="block">{job.task_name} · <span className="money">{sym} {job.daily_rate}</span></strong>
        <small className="muted">{job.location_text}</small></div>
      <SpeakerButton text={t("inv.speak", { task: job.task_name, place: job.location_text, rate: job.daily_rate })} /></div>
    <div className="btn-row"><BigButton small onClick={() => onOpen(job.id)}>{t("inv.see")}</BigButton>
      <BigButton small tone="gray" onClick={async () => { try { await api(`/jobs/${job.id}/decline-invite`, { method: "POST", body: {}, retries: 0 }); } catch { /* */ } inv.reload(true); }}>{t("inv.no")}</BigButton></div>
  </div>)}</div>;
}

/* ============================== hirer: workers free today ============================== */
export function FreeWorkers({ location }: { location: WorkLocation }) {
  const { t, lang } = useI18n();
  const { me, country } = useSession();
  const p = me?.profile;
  const point = location.point || (p?.lat != null ? { lat: p.lat, lon: p.lon } : country?.places[0]);
  const [trade, setTrade] = useState("");
  const [inviting, setInviting] = useState("");
  const [sent, setSent] = useState<Record<string, string>>({});
  const list = useAsync(() => point ? api<any[]>(`/workers/available?lat=${point.lat}&lon=${point.lon}&radius_km=25${trade ? "&trade=" + trade : ""}`) : Promise.resolve([]), [point?.lat, point?.lon, trade], true);
  const jobs = useAsync(() => api<any[]>("/jobs/mine"), []);
  const openJobs = jobs.data?.filter((j) => ["open", "offers", "assigned"].includes(j.status) && !j.booking_expired && j.booked < j.headcount) || [];
  const tn = (c: string) => country?.trades.find((x) => x.code === c)?.names[lang] || c;
  const invite = async (wid: string, jid: string) => {
    try { await api(`/jobs/${jid}/invite`, { method: "POST", body: { worker_id: wid }, retries: 0 }); setSent((s) => ({ ...s, [wid]: "ok" })); }
    catch (e) { setSent((s) => ({ ...s, [wid]: errMsg(t, e) })); }
    setInviting("");
  };
  return <div className="page">
    <ScreenHeader title={t("free.title")} speakText={list.data?.length ? t("free.speak", { n: list.data.length }) : t("free.none")} />
    <div className="page-body">
      <p className="muted">{t("free.hint")}</p>
      <div className="chips-row" role="group"><button className={"chip" + (!trade ? " on" : "")} onClick={() => setTrade("")}>{t("free.all")}</button>
        {country?.trades.map((tr) => <button key={tr.code} className={"chip" + (trade === tr.code ? " on" : "")} onClick={() => setTrade(tr.code)}>{tr.names[lang] || tr.names.en}</button>)}</div>
      {list.loading && !list.data && <Skeleton n={2} />}
      {!!list.error && <ErrorRetry error={list.error} onRetry={list.reload} />}
      {list.data && !list.data.length && <div className="empty-state"><span className="art">🌙</span><p>{t("free.none")}</p></div>}
      {list.data?.map((w) => <div key={w.worker_id} className="card">
        <div className="person"><span className="avatar" aria-hidden>👷</span>
          <div className="grow"><strong>{w.first_name} <TierBadge tier={w.tier} /></strong><small className="muted">🟢 {t("free.today")} · {t("ui.job.km", { km: w.distance_km })}</small></div></div>
        <div className="skill-list">{w.trades.map((c: string) => <span key={c} className="skill"><TradeIcon code={c} />{tn(c)}{w.skills.find((s: any) => s.trade === c) ? " 🏅" + w.skills.find((s: any) => s.trade === c).endorsements : ""}</span>)}</div>
        {sent[w.worker_id] === "ok" ? <p className="status-line ok">✔ {t("free.invited_said")}</p>
          : sent[w.worker_id] ? <p className="status-line bad">{sent[w.worker_id]}</p>
          : inviting === w.worker_id ? (openJobs.length ? <div className="grid gap-2"><small className="muted">{t("free.pick_job")}</small>
            {openJobs.map((j) => <BigButton key={j.id} small tone="gray" onClick={() => invite(w.worker_id, j.id)}>{j.task_name} · {j.location_text}</BigButton>)}</div>
            : <Link className="btn btn-gold btn-sm" to="/">{t("free.post_first")}</Link>)
          : <BigButton small icon="📣" onClick={() => setInviting(w.worker_id)}>{t("free.invite")}</BigButton>}
      </div>)}
    </div>
  </div>;
}

/* ============================== hirer: my team (thekedar crew) ============================== */
type Member = { worker_id: string; name: string; first_name: string; phone: string; has_app: boolean; trades: string[]; available: boolean; checked_in_today: boolean; tier: Tier };
type TeamT = { id: string; name: string; members: Member[] };

export function TeamPage() {
  const { t, bcp47 } = useI18n();
  const { country } = useSession();
  const teams = useAsync(() => api<TeamT[]>("/teams"), [], true);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [mname, setMname] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [days, setDays] = useState(7);
  const team = teams.data?.[0];
  const pay = useAsync(() => team ? api<any>(`/teams/${team.id}/payroll?days=${days}`) : Promise.resolve(null), [team?.id, days, team?.members.length]);
  const sym = country?.currency.symbol || "";
  const m = (n: number) => `${sym} ${n.toLocaleString("en-US")}`;
  const run = async (fn: () => Promise<any>) => { setErr(null); try { await fn(); await teams.reload(true); } catch (e) { setErr(e); } };
  const csv = async () => {
    const r = await fetch(`/api/teams/${team!.id}/payroll?days=${days}&format=csv`, { headers: { Authorization: `Bearer ${getToken()}` } });
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a"); a.href = url; a.download = `payroll-${days}d.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000);
  };
  const present = team?.members.filter((x) => x.checked_in_today).length || 0;
  return <div className="page">
    <ScreenHeader title={team ? team.name : t("team.title")} speakText={team ? t("team.speak", { n: team.members.length, present }) : t("team.intro")} />
    <div className="page-body">
      {teams.loading && !teams.data && <Skeleton n={2} />}
      {!!err && <p className="status-line bad" role="alert">{errMsg(t, err)}</p>}
      {teams.data && !team && <div className="card"><h2>👥 {t("team.create")}</h2><p className="muted">{t("team.intro")}</p>
        <label className="field">{t("team.name")}<input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder={t("team.name_ph")} /></label>
        <BigButton disabled={!name.trim()} onClick={() => run(() => api("/teams", { method: "POST", body: { name }, retries: 0 }))}>{t("team.create")}</BigButton></div>}
      {team && <>
        <div className="ledger-sum"><div><small>{t("team.members")}</small><b>{team.members.length}</b></div><div><small>{t("team.present")}</small><b>{present}</b></div>
          <div className="bal"><small>{t("team.owed")}</small><b>{pay.data ? m(pay.data.total_balance) : "…"}</b></div></div>
        {team.members.map((x) => <div key={x.worker_id} className="card">
          <div className="person"><span className="avatar" aria-hidden>👷</span>
            <div className="grow"><strong>{x.name} <TierBadge tier={x.tier} /></strong>
              <small className="muted"><a dir="ltr" href={`tel:${x.phone}`}>{x.phone}</a>{!x.has_app && " · " + t("team.no_app")}</small></div>
            {x.checked_in_today ? <span className="pill">✅ {t("team.here")}</span> : x.available ? <span className="pill blue">🟢 {t("free.today")}</span> : <span className="pill gray">—</span>}</div>
          <button className="link-btn" onClick={() => run(() => api(`/teams/${team.id}/members/${x.worker_id}`, { method: "DELETE", retries: 0 }))}>{t("team.remove")}</button>
        </div>)}
        <div className="card soft"><h2>➕ {t("team.add")}</h2>
          <label className="field">{t("team.phone")}<input dir="ltr" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="03xx xxxxxxx" /></label>
          <label className="field">{t("team.member_name")}<input value={mname} maxLength={80} onChange={(e) => setMname(e.target.value)} /></label>
          <small className="muted">{t("team.add_hint")}</small>
          <BigButton disabled={phone.replace(/\D/g, "").length < 7} onClick={() => run(async () => { await api(`/teams/${team.id}/members`, { method: "POST", body: { phone, name: mname || null }, retries: 0 }); setPhone(""); setMname(""); })}>{t("team.add")}</BigButton></div>
        <section className="card"><div className="card-row"><h2 className="grow">🧾 {t("team.payroll")}</h2>
          {pay.data && <SpeakerButton text={t("team.payroll_speak", { days, amount: m(pay.data.total_balance) })} />}</div>
          <div className="chips-row">{[7, 15, 30].map((d) => <button key={d} className={"chip" + (d === days ? " on" : "")} onClick={() => setDays(d)}>{t("team.days", { n: d })}</button>)}</div>
          {pay.data?.rows.map((r: any) => <div key={r.worker_id} className="ledger-row"><span className="ico">👷</span>
            <div className="grow"><strong>{r.name}</strong><small>{t("team.row", { days: r.days, earned: m(r.earned), received: m(r.received) })}</small></div><b className="money">{m(r.balance)}</b></div>)}
          <BigButton small tone="gray" icon="⬇️" onClick={csv}>{t("team.csv")}</BigButton>
          <small className="muted">{new Date().toLocaleDateString(bcp47)}</small></section>
      </>}
    </div>
  </div>;
}

/* ============================== both: help, safety and settings ============================== */
export function HelpPage() {
  const { t, lang, setLang, bcp47 } = useI18n();
  const { me, country, logout, refresh } = useSession();
  const [params, setParams] = useSearchParams();
  const [armed, setArmed] = useState(params.get("sos") === "1");
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const sc = (me as any)?.safety_contact;
  const [cname, setCname] = useState(sc?.name || "");
  const [cphone, setCphone] = useState(sc?.phone || "");
  const [saved, setSaved] = useState("");
  const [auto, setAuto] = useState(autoVoiceOn());
  const emergency = res?.emergency_number || country?.emergency_number || "";
  useEffect(() => { if (params.get("sos") === "1") { setArmed(true); speak(t("help.sos_armed"), bcp47, lang); setParams({}, { replace: true }); } /* eslint-disable-next-line */ }, []);
  const sos = async () => {
    if (!armed) { setArmed(true); speak(t("help.sos_armed"), bcp47, lang); return; }
    setBusy(true); const p = await here(5000);
    try { const r = await api("/safety/sos", { method: "POST", body: p || {}, retries: 2 }); setRes(r); speak(t("help.sos_sent"), bcp47, lang); }
    catch { setRes({ failed: true }); } finally { setBusy(false); setArmed(false); }
  };
  const examples = t(me?.role === "worker" ? "help.cmds.worker" : "help.cmds.hirer").split("|");
  return <div className="page">
    <ScreenHeader title={t("help.title")} speakText={t("help.speak")} />
    <div className="page-body">
      <section className="card warn" style={{ justifyItems: "center", textAlign: "center" }}>
        <h2>🆘 {t("help.sos_title")}</h2>
        <button className={"sos-btn" + (armed ? " armed" : "")} onClick={sos} disabled={busy}><span aria-hidden>🆘</span>{armed ? t("help.sos_confirm") : t("help.sos")}</button>
        {armed && <button className="link-btn" onClick={() => setArmed(false)}>{t("ui.back")}</button>}
        <p className="muted">{t("help.sos_hint")}</p>
        {res && !res.failed && <p className="status-line ok">✔ {t("help.sos_done", { who: (res.notified as string[]).map((w) => t("help.who." + w)).join("، ") || t("help.who.none") })}</p>}
        {res?.failed && <p className="status-line bad">{t("ui.error.network")}</p>}
        {emergency && <a className="btn btn-red" href={`tel:${emergency}`}><span className="ico" aria-hidden>📞</span>{t("help.call", { n: emergency })}</a>}
      </section>

      <section className="card"><h2>🛡️ {t("help.contact")}</h2><p className="muted">{t("help.contact_hint")}</p>
        <label className="field">{t("team.member_name")}<input value={cname} onChange={(e) => setCname(e.target.value)} maxLength={60} /></label>
        <label className="field">{t("team.phone")}<input dir="ltr" inputMode="tel" value={cphone} onChange={(e) => setCphone(e.target.value)} /></label>
        {saved && <p className={"status-line " + (saved === "ok" ? "ok" : "bad")}>{saved === "ok" ? "✔ " + t("help.saved") : saved}</p>}
        <BigButton small disabled={!cname.trim() || !cphone.trim()} onClick={async () => { try { await api("/me/safety-contact", { method: "PUT", body: { name: cname, phone: cphone }, retries: 0 }); setSaved("ok"); refresh(); } catch (e) { setSaved(errMsg(t, e)); } }}>{t("help.save")}</BigButton></section>

      <section className="card"><h2>🎙️ {t("help.voice_title")}</h2><p className="muted">{t("help.voice_hint")}</p>
        {examples.map((ex) => <div key={ex} className="card-row"><span className="grow text-lg">🗣️ {ex}</span><SpeakerButton text={ex} /></div>)}</section>

      <section className="card"><h2>⚙️ {t("help.settings")}</h2>
        <button className={"free-toggle" + (auto ? " on" : "")} onClick={() => { setAutoVoice(!auto); setAuto(!auto); }} aria-pressed={auto}>
          <span className="knob"><i /></span><span className="grow"><strong>{t("help.auto_voice")}</strong><small>{t("help.auto_voice_hint")}</small></span></button>
        <div className="btn-row"><BigButton small tone={lang === "ur" ? "green" : "gray"} onClick={() => setLang("ur")}>اردو</BigButton><BigButton small tone={lang === "en" ? "green" : "gray"} onClick={() => setLang("en")}>English</BigButton></div>
        <BigButton small tone="gray" onClick={logout}>{t("ui.me.logout")}</BigButton></section>
    </div>
  </div>;
}

/* ============================== public: shared Kaam Card ============================== */
export function PublicCard() {
  const { token } = useParams();
  const { t, bcp47, lang } = useI18n();
  const nav = useNavigate();
  const c = useAsync(() => api<any>(`/public/card/${token}`), [token]);
  const meta = useAsync(() => api<{ code: string }>("/meta/default-country").then((x) => api<any>(`/meta/country/${x.code}`)), []);
  const tradeName = (code: string) => meta.data?.trades.find((x: any) => x.code === code)?.names[lang] || code;
  if (c.loading) return <Skeleton n={2} />;
  if (c.error) return <div className="public-card"><p className="status-line bad">{(c.error as ApiError).status === 404 ? t("share.not_found") : t("ui.error.generic")}</p></div>;
  const d = c.data;
  return <div className="public-card kaam-page">
    <header className="kaam-head" style={{ background: "linear-gradient(100deg,#0f2a23,#164b3e)", borderRadius: 22, margin: "0 0 14px" }}>
      <div><small>{t("card.title")}</small><h1>{d.first_name}</h1></div>
      <SpeakerButton text={t("share.speak", { name: d.first_name, tier: t("tier." + d.tier.code), jobs: d.tier.stats.jobs })} auto /></header>
    <section className="kaam-card" style={{ ["--tier" as any]: d.tier.color }}>
      <div className="kaam-card-top"><span className="kaam-icon" aria-hidden>{d.tier.icon}</span><div><small>{t("tier.level")}</small><strong>{t("tier." + d.tier.code)}</strong></div>{d.verified_phone && <span className="pill gold">✔ {t("share.verified")}</span>}</div>
      <div className="kaam-stats"><div><b>{d.tier.stats.jobs}</b><small>{t("card.jobs")}</small></div><div><b>{d.tier.stats.rating ? "★ " + d.tier.stats.rating.toFixed(1) : "—"}</b><small>{t("card.rating")}</small></div><div><b>{d.tier.stats.hirers}</b><small>{t("card.hirers")}</small></div></div>
    </section>
    {d.skills.length > 0 && <section className="card" style={{ marginTop: 14 }}><h2>🏅 {t("skill.title")}</h2><div className="skill-list">{d.skills.map((s: any) => <span key={s.trade} className="skill"><TradeIcon code={s.trade} />{tradeName(s.trade)} · {t("skill.count", { n: s.endorsements })}</span>)}</div></section>}
    <section className="history" style={{ marginTop: 14 }}><h2>{t("card.history")}</h2>
      {d.history.map((h: any, i: number) => <div key={i} className="history-row"><span className="history-icon"><TradeIcon code={h.task} size={30} /></span>
        <div><strong>{tradeName(h.task)}</strong><small>{new Date(h.start_at).toLocaleDateString(bcp47, { day: "numeric", month: "short", year: "numeric" })} · {t("card.days", { n: h.days })}</small><small className="proof">✔ {t("card.proof", { id: h.proof })}</small></div>
        <div className="history-end">{h.rating ? <em>{"★".repeat(h.rating)}</em> : null}</div></div>)}</section>
    <p className="kaam-share">{t("share.footer")}</p>
    <BigButton tone="gray" onClick={() => nav("/")}>{t("share.open_app")}</BigButton>
    <span hidden>{lang}</span>
  </div>;
}
