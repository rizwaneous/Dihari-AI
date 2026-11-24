import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { Icon } from "./Icon";

type Account = { role: "hirer" | "worker"; name: string; phone: string };
let cached: Promise<{ enabled: boolean; accounts: Account[] }> | null = null;
const demoInfo = () => (cached ??= api<{ enabled: boolean; accounts: Account[] }>("/auth/demo").catch(() => ({ enabled: false, accounts: [] })));

function useDemo() {
  const [info, setInfo] = useState<{ enabled: boolean; accounts: Account[] }>({ enabled: false, accounts: [] });
  useEffect(() => { let live = true; demoInfo().then((d) => live && setInfo(d)); return () => { live = false; }; }, []);
  return info;
}

async function loginAs(role: string) {
  const r = await api<{ token: string }>("/auth/demo-login", { method: "POST", body: { role }, retries: 0 });
  setToken(r.token);
}

/** Guest screen: two big one-tap demo accounts. */
export function DemoEntry() {
  const { t } = useI18n();
  const { refresh } = useSession();
  const { enabled, accounts } = useDemo();
  const [busy, setBusy] = useState("");
  if (!enabled) return null;
  const go = async (role: string) => { setBusy(role); try { await loginAs(role); await refresh(); } finally { setBusy(""); } };
  return <div className="demo-box">
    <span className="eyebrow"><i />{t("demo.title")}</span>
    <p className="muted">{t("demo.hint")}</p>
    <div className="demo-cards">{accounts.map((a) =>
      <button key={a.role} className={"demo-card " + a.role} disabled={!!busy} onClick={() => go(a.role)}>
        <span className="demo-avatar" aria-hidden="true">{a.role === "hirer" ? "🏗️" : "👷"}</span>
        <strong>{t(a.role === "hirer" ? "demo.as_hirer" : "demo.as_worker")}</strong>
        <small>{a.name}</small>
        <span className="demo-go">{busy === a.role ? "…" : <Icon name="arrow" />}</span>
      </button>)}</div>
  </div>;
}

/** Header button: jump between the two demo accounts in one tap. */
export function DemoSwitch() {
  const { t } = useI18n();
  const { me, refresh } = useSession();
  const { enabled, accounts } = useDemo();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const mine = accounts.find((a) => a.role === me?.role);
  if (!enabled || !me || !mine) return null;
  const other = me.role === "hirer" ? "worker" : "hirer";
  const go = async () => { setBusy(true); try { await loginAs(other); nav("/"); await refresh(); } finally { setBusy(false); } };
  return <button className="demo-switch" disabled={busy} onClick={go} title={t("demo.switch", { role: t("demo.role." + other) })}>
    <span aria-hidden="true">{other === "hirer" ? "🏗️" : "👷"}</span>{t("demo.switch", { role: t("demo.role." + other) })}
  </button>;
}
