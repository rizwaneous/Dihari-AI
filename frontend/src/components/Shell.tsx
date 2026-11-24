import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { canListen, listen, speak, stopSpeaking, type Listener } from "../voice";

/** Phone position, or null after a short wait. Never throws. */
export function here(timeout = 6000): Promise<{ lat: number; lon: number } | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    const done = setTimeout(() => resolve(null), timeout + 500);
    navigator.geolocation.getCurrentPosition(
      (p) => { clearTimeout(done); resolve({ lat: p.coords.latitude, lon: p.coords.longitude }); },
      () => { clearTimeout(done); resolve(null); }, { enableHighAccuracy: true, timeout, maximumAge: 60000 });
  });
}

/** Lets pages refresh when the assistant changed something (e.g. "free today"). */
export const emit = (name: string) => window.dispatchEvent(new CustomEvent("dihari:" + name));
export function useBus(name: string, fn: () => void) {
  useEffect(() => { const h = () => fn(); window.addEventListener("dihari:" + name, h); return () => window.removeEventListener("dihari:" + name, h); }, [name, fn]);
}

type Tab = { to: string; icon: string; label: string; badge?: number; cls?: string };

function BottomNav({ tabs }: { tabs: Tab[] }) {
  return <nav className="bottom-nav" aria-label="main">
    {tabs.map((tb) => <NavLink key={tb.to} to={tb.to} end={tb.to === "/"} className={({ isActive }) => (isActive ? "active " : "") + (tb.cls || "")}>
      <span className="nav-ico" aria-hidden="true">{tb.icon}</span><span>{tb.label}</span>
      {!!tb.badge && <span className="dot">{tb.badge}</span>}
    </NavLink>)}
  </nav>;
}

/** The logged-in frame: page, bottom tabs, and the always-there voice button. */
export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { me } = useSession();
  const [invites, setInvites] = useState(0);
  const worker = me?.role === "worker";
  useEffect(() => {
    if (!worker) return;
    let live = true;
    const load = () => !document.hidden && api<any[]>("/my/invites", { retries: 0 }).then((r) => live && setInvites(r.length)).catch(() => {});
    load(); const id = setInterval(load, 20000);
    return () => { live = false; clearInterval(id); };
  }, [worker]);
  const tabs: Tab[] = worker
    ? [{ to: "/", icon: "🧭", label: t("nav.jobs"), badge: invites }, { to: "/work", icon: "🛠️", label: t("nav.mywork") },
       { to: "/me", icon: "🪪", label: t("nav.card") }, { to: "/help", icon: "🆘", label: t("nav.help"), cls: "sos-tab" }]
    : [{ to: "/", icon: "🧭", label: t("nav.home") }, { to: "/jobs-mine", icon: "📋", label: t("nav.requests") },
       { to: "/workers", icon: "👷", label: t("nav.free") }, { to: "/team", icon: "👥", label: t("nav.team") },
       { to: "/help", icon: "🆘", label: t("nav.help"), cls: "sos-tab" }];
  return <div className="shell">{children}<VoiceAssistant /><BottomNav tabs={tabs} /></div>;
}

type Reply = { action: string; source: string; text: string; say: string };

/** Floating mic: say what you want ("kaam chahiye", "aaj farigh hoon", "mera hisaab", "pohanch gaya")
 *  and the app answers aloud and takes you there. Falls back to typing when the phone can't listen. */
export function VoiceAssistant() {
  const { t, bcp47, lang } = useI18n();
  const { me } = useSession();
  const nav = useNavigate();
  const loc = useLocation();
  const [state, setState] = useState<"idle" | "listening" | "thinking">("idle");
  const [li, setLi] = useState<Listener | null>(null);
  const [open, setOpen] = useState(false);
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("");
  const [typing, setTyping] = useState(false);
  const [txt, setTxt] = useState("");
  useEffect(() => { setOpen(false); }, [loc.pathname]);
  const say = (s: string) => { setReply(s); speak(s, bcp47, lang); };

  async function act(r: Reply, text: string) {
    say(r.say);
    const worker = me?.role === "worker";
    switch (r.action) {
      case "find_jobs": case "invites": nav("/"); break;
      case "set_available": {
        const p = await here(4000);
        try { await api("/me/available", { method: "POST", body: { available: true, ...(p || {}) }, retries: 0 }); emit("available"); } catch { say(t("ui.error.generic")); }
        nav("/"); break;
      }
      case "my_work": nav("/work"); break;
      case "check_in": nav("/work?do=check_in"); break;
      case "check_out": nav("/work?do=check_out"); break;
      case "hisaab": nav(worker ? "/work?do=hisaab" : "/jobs-mine"); break;
      case "kaam_card": nav("/me"); break;
      case "sos": nav("/help?sos=1"); break;
      case "help": nav("/help"); break;
      case "post_job": nav("/post/assisted", { state: { text } }); break;
      case "free_workers": nav("/workers"); break;
      case "my_jobs": nav("/jobs-mine"); break;
      case "team": nav("/team"); break;
      default: break;
    }
  }

  async function handle(text: string) {
    if (!text.trim()) { setState("idle"); return; }
    setHeard(text); setState("thinking"); setTyping(false);
    try { const r = await api<Reply>("/voice/command", { method: "POST", body: { transcript: text, lang }, retries: 1 }); await act(r, text); }
    catch { say(t("ui.error.network")); }
    finally { setState("idle"); }
  }

  async function start() {
    stopSpeaking(); setOpen(true); setHeard(""); setReply("");
    if (!canListen()) { setTyping(true); return; }
    try {
      const l = await listen(bcp47, lang); setLi(l); setState("listening");
      l.result.then((s) => { setLi(null); handle(s); })
        .catch(() => { setLi(null); setState("idle"); setReply(t("voice.not_heard")); setTyping(true); });
    } catch { setState("idle"); setTyping(true); }
  }
  const tap = () => (li ? li.stop() : state === "idle" ? start() : undefined);
  if (!me) return null;
  return <>
    {open && <div className="voice-bubble" role="dialog" aria-live="polite">
      <button className="close" aria-label={t("ui.close")} onClick={() => { li?.stop(); stopSpeaking(); setOpen(false); }}>✕</button>
      {state === "listening" ? <p className="reply">{t("voice.listening")}<span className="wave"><i /><i /><i /><i /></span></p>
        : state === "thinking" ? <p className="reply">{t("voice.thinking")}</p>
        : !heard && !reply ? <p className="reply">{t("voice.prompt")}</p> : null}
      {heard && <p className="heard">“{heard}”</p>}
      {reply && state !== "thinking" && <p className="reply">{reply}</p>}
      {!heard && state === "idle" && <p className="heard">{t(me.role === "worker" ? "voice.examples.worker" : "voice.examples.hirer")}</p>}
      {typing && <form className="row" onSubmit={(e) => { e.preventDefault(); handle(txt); setTxt(""); }}>
        <textarea value={txt} onChange={(e) => setTxt(e.target.value)} placeholder={t("ui.post.type_ph")} aria-label={t("ui.post.type")} />
        <button className="go" disabled={!txt.trim()}>{t("ui.post.send")}</button>
        {canListen() && <button type="button" onClick={() => { setTyping(false); start(); }}>🎤 {t("voice.again")}</button>}
      </form>}
      {!typing && state === "idle" && (heard || reply) && <div className="row"><button className="go" onClick={start}>🎤 {t("voice.again")}</button><button onClick={() => setTyping(true)}>⌨️ {t("ui.post.type")}</button></div>}
    </div>}
    <button className={"voice-fab " + state} onClick={tap} aria-label={t("voice.fab")} title={t("voice.fab")}>
      <span aria-hidden="true">{state === "listening" ? "⏹" : "🎙️"}</span>
    </button>
  </>;
}
