import { useState } from "react";
import { BigButton } from "../components/ui";
import { api } from "../api";
import { ErrorRetry, Skeleton, SpeakerButton, useAsync } from "../components/ui";
import { TierBadge, TierProgress, type Tier } from "../components/Tier";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { TradeIcon } from "../components/TradeIcon";
import { ProfileForm } from "./Onboarding";

type Stats = { earned_week: number; earned_month: number; earned_total: number; owed: number; tier: Tier;
  skills?: { trade: string; endorsements: number; years: number | null }[];
  history: { job_id: string; task: string; location_text: string; start_at: string; days: number; daily_rate: number; rating: number | null; paid: string | null; proof: string }[] };

/** The worker's "Kaam Card": level, earnings and a work history built only from agreed, completed jobs. */
export function KaamCard() {
  const { t, bcp47, lang } = useI18n();
  const { me, country, logout } = useSession();
  const { data, error, loading, reload } = useAsync(() => api<Stats>("/my/stats"), [], true);
  const [edit, setEdit] = useState(false);
  if (edit) return <ProfileForm onSaved={() => setEdit(false)} />;
  const sym = country?.currency.symbol || "";
  const money = (n: number) => `${sym} ${n.toLocaleString(bcp47)}`;
  const trade = (c: string) => { const tr = country?.trades.find((x) => x.code === c); return { icon: tr?.icon || "🛠️", name: tr?.names[lang] || tr?.names.en || c }; };
  const name = me?.name || "";
  return <div className="kaam-page">
    <header className="kaam-head">
      <div><small>{t("card.title")}</small><h1>{name}</h1></div>
      {data && <SpeakerButton text={t("card.speak", { name, tier: t("tier." + data.tier.code), amount: data.earned_month, jobs: data.tier.stats.jobs })} />}
    </header>
    {loading && !data && <Skeleton n={2} />}
    {!!error && <ErrorRetry error={error} onRetry={reload} />}
    {data && <>
      <section className="kaam-card" style={{ ["--tier" as any]: data.tier.color }}>
        <div className="kaam-card-top"><span className="kaam-icon" aria-hidden="true">{data.tier.icon}</span>
          <div><small>{t("tier.level")}</small><strong>{t("tier." + data.tier.code)}</strong></div>
          <span className="brand-mark" aria-hidden="true">d</span></div>
        <div className="kaam-stats">
          <div><b>{data.tier.stats.jobs}</b><small>{t("card.jobs")}</small></div>
          <div><b>{data.tier.stats.rating ? "★ " + data.tier.stats.rating.toFixed(1) : "—"}</b><small>{t("card.rating")}</small></div>
          <div><b>{data.tier.stats.hirers}</b><small>{t("card.hirers")}</small></div>
        </div>
        <TierProgress tier={data.tier} />
        <p className="kaam-perk">{t("tier.perks")}</p>
      </section>
      <section className="earn-grid">
        <div className="earn main"><small>{t("card.month")}</small><b>{money(data.earned_month)}</b></div>
        <div className="earn"><small>{t("card.week")}</small><b>{money(data.earned_week)}</b></div>
        <div className="earn"><small>{t("card.total")}</small><b>{money(data.earned_total)}</b></div>
        {data.owed > 0 && <div className="earn owed"><small>{t("card.owed")}</small><b>{money(data.owed)}</b></div>}
      </section>
      {!!data.skills?.length && <section className="card" style={{ marginBottom: 14 }}><h2>🏅 {t("skill.title")}</h2>
        <div className="skill-list">{data.skills!.map((s) => <span key={s.trade} className="skill"><TradeIcon code={s.trade} />{trade(s.trade).name} · {t("skill.count", { n: s.endorsements })}</span>)}</div></section>}
      <section className="history">
        <h2>{t("card.history")}</h2>
        {!data.history.length && <p className="muted">{t("card.empty")}</p>}
        {data.history.map((h) => { const tr = trade(h.task); return <div key={h.job_id} className="history-row">
          <span className="history-icon" aria-hidden="true"><TradeIcon code={h.task} size={30} /></span>
          <div><strong>{tr.name}</strong><small>{h.location_text} · {new Date(h.start_at).toLocaleDateString(bcp47, { day: "numeric", month: "short" })} · {t("card.days", { n: h.days })}</small>
            <small className="proof">✔ {t("card.proof", { id: h.proof })}</small></div>
          <div className="history-end"><b>{money(h.daily_rate * h.days)}</b>
            {h.paid === "unpaid" ? <em className="unpaid">{t("card.unpaid")}</em> : h.rating ? <em>{"★".repeat(h.rating)}</em> : null}</div>
        </div>; })}
        <ShareCard />
      </section>
    </>}
    <div className="kaam-actions"><button className="secondary" onClick={() => setEdit(true)}>✏️ {t("card.edit")}</button>
      <button className="secondary" onClick={logout}>{t("ui.me.logout")}</button></div>
  </div>;
}

/** A link anyone can open to see this card (no addresses, no phone). Shares through WhatsApp or the phone's share sheet. */
function ShareCard() {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [copied, setCopied] = useState(false);
  const get = async () => { const r = await api<{ path: string }>("/my/card-link"); const u = location.origin + r.path; setUrl(u); return u; };
  const share = async () => {
    const u = url || await get();
    const text = t("share.msg", { url: u });
    try { if ((navigator as any).share) { await (navigator as any).share({ title: t("card.title"), text, url: u }); return; } } catch { /* cancelled */ }
    window.open("https://wa.me/?text=" + encodeURIComponent(text), "_blank", "noopener");
  };
  return <div className="kaam-share" style={{ display: "grid", gap: 10 }}>
    <p>{t("card.share")}</p>
    <BigButton tone="green" icon="📤" onClick={share}>{t("share.button")}</BigButton>
    {url && <div className="card-row"><input readOnly dir="ltr" value={url} className="grow" style={{ minHeight: 44, borderRadius: 10, padding: "0 10px", border: "1px solid #ccc" }} onFocus={(e) => e.target.select()} />
      <button className="chip" onClick={async () => { try { await navigator.clipboard.writeText(url); setCopied(true); } catch { /* */ } }}>{copied ? "✔" : t("share.copy")}</button></div>}
    {!url && <button className="link-btn" onClick={get}>{t("share.show_link")}</button>}
  </div>;
}
