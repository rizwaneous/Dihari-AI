import { useState } from "react";
import { api } from "../api";
import { ErrorRetry, Skeleton, SpeakerButton, useAsync } from "../components/ui";
import { TierBadge, TierProgress, type Tier } from "../components/Tier";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { ProfileForm } from "./Onboarding";

type Stats = { earned_week: number; earned_month: number; earned_total: number; owed: number; tier: Tier;
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
      <section className="history">
        <h2>{t("card.history")}</h2>
        {!data.history.length && <p className="muted">{t("card.empty")}</p>}
        {data.history.map((h) => { const tr = trade(h.task); return <div key={h.job_id} className="history-row">
          <span className="history-icon" aria-hidden="true">{tr.icon}</span>
          <div><strong>{tr.name}</strong><small>{h.location_text} · {new Date(h.start_at).toLocaleDateString(bcp47, { day: "numeric", month: "short" })} · {t("card.days", { n: h.days })}</small>
            <small className="proof">✔ {t("card.proof", { id: h.proof })}</small></div>
          <div className="history-end"><b>{money(h.daily_rate * h.days)}</b>
            {h.paid === "unpaid" ? <em className="unpaid">{t("card.unpaid")}</em> : h.rating ? <em>{"★".repeat(h.rating)}</em> : null}</div>
        </div>; })}
        <p className="kaam-share">{t("card.share")}</p>
      </section>
    </>}
    <div className="kaam-actions"><button className="secondary" onClick={() => setEdit(true)}>✏️ {t("card.edit")}</button>
      <button className="secondary" onClick={logout}>{t("ui.me.logout")}</button></div>
  </div>;
}
