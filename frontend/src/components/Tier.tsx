import { useI18n } from "../i18n";

export type Tier = { code: string; level: number; icon: string; color: string; progress: number;
  stats: { jobs: number; show_up: number | null; rating: number | null; hirers: number };
  next: { code: string; icon: string; needs: { jobs?: number; hirers?: number; rating?: number; show_up?: number } } | null };

/** Picture-first badge: the icon and colour carry the meaning, the word is a bonus for readers. */
export function TierBadge({ tier, size = "sm" }: { tier?: Tier | null; size?: "sm" | "lg" }) {
  const { t } = useI18n();
  if (!tier) return null;
  return <span className={"tier-badge " + size} style={{ ["--tier" as any]: tier.color }} title={t("tier." + tier.code)}>
    <span aria-hidden="true">{tier.icon}</span>{t("tier." + tier.code)}</span>;
}

export function TierProgress({ tier }: { tier: Tier }) {
  const { t } = useI18n();
  const n = tier.next;
  const tips = n ? [
    n.needs.jobs && t("tier.next_jobs", { n: n.needs.jobs, tier: t("tier." + n.code) }),
    n.needs.hirers && t("tier.next_hirers", { n: n.needs.hirers }),
    n.needs.rating && t("tier.next_rating", { r: n.needs.rating }),
    n.needs.show_up && t("tier.next_show_up", { pct: Math.round(n.needs.show_up * 100) }),
  ].filter(Boolean) as string[] : [];
  return <div className="tier-progress">
    <div className="tier-steps" aria-hidden="true">{["🪖", "🥈", "🥇", "💎"].map((ic, i) =>
      <span key={i} className={i <= tier.level ? "on" : ""}>{ic}</span>)}</div>
    {n ? <><div className="bar"><i style={{ width: `${Math.max(6, tier.progress * 100)}%` }} /></div>
      <ul>{tips.map((s) => <li key={s}>{s}</li>)}</ul></> : <p className="tier-top">{t("tier.top")}</p>}
  </div>;
}
