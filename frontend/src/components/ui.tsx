import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { ApiError } from "../api";
import { useI18n } from "../i18n";
import { canListen, listen, speak, stopSpeaking, type Listener } from "../voice";
import { DemoSwitch } from "./Demo";

type Tone = "green" | "red" | "gray" | "blue";
const tones: Record<Tone, string> = {
  green: "bg-green-700 text-white active:bg-green-900", red: "bg-red-700 text-white active:bg-red-900",
  gray: "bg-gray-200 text-black active:bg-gray-300 border-2 border-gray-500", blue: "bg-blue-800 text-white active:bg-blue-950",
};

export function BigButton({ tone = "green", icon, children, onClick, disabled, className = "" }: { tone?: Tone; icon?: ReactNode; children: ReactNode; onClick?: () => void; disabled?: boolean; className?: string }) {
  return (
    <button onClick={onClick} disabled={disabled} className={`w-full min-h-[72px] rounded-2xl px-4 text-2xl font-bold flex items-center justify-center gap-3 disabled:opacity-50 ${tones[tone]} ${className}`}>
      {icon && <span aria-hidden className="text-3xl">{icon}</span>}{children}
    </button>
  );
}

export function SpeakerButton({ text, load, auto }: { text?: string; load?: () => Promise<string>; auto?: boolean }) {
  const { t, bcp47, lang } = useI18n();
  const [on, setOn] = useState(false);
  const play = async () => {
    setOn(true);
    try { const s = load ? await load() : text || ""; if (s) await speak(s, bcp47, lang); } catch { /* visual fallback remains */ }
    setTimeout(() => setOn(false), 800);
  };
  useEffect(() => { if (auto && (text || load)) play(); return () => stopSpeaking(); /* eslint-disable-next-line */ }, [text, auto]);
  return (
    <button aria-label={t("ui.speak")} onClick={on ? () => { stopSpeaking(); setOn(false); } : play}
      className={`min-w-[64px] min-h-[64px] rounded-full text-3xl flex items-center justify-center border-4 ${on ? "bg-blue-800 text-white border-blue-950" : "bg-blue-100 border-blue-800"}`}>
      <span aria-hidden>🔊</span>
    </button>
  );
}

export function ScreenHeader({ title, speakText, auto }: { title: string; speakText: string; auto?: boolean }) {
  return (
    <header className="flex items-center justify-between gap-3 p-4 bg-brand text-white sticky top-0 z-10">
      <h1 className="text-2xl font-bold">{title}</h1>
      <div className="flex items-center gap-2"><DemoSwitch /><SpeakerButton text={speakText || title} auto={auto} /></div>
    </header>
  );
}

export function Skeleton({ n = 3 }: { n?: number }) {
  return <div className="space-y-4 p-4" aria-busy>{Array.from({ length: n }).map((_, i) => <div key={i} className="skeleton h-40" />)}</div>;
}

export function ErrorRetry({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const { t } = useI18n();
  const e = error as ApiError;
  const msg = e?.status === 0 ? t("ui.error.network") : e?.status === 429 ? t("ui.error.rate_limited") : t("ui.error.generic");
  return (
    <div role="alert" className="m-4 p-4 rounded-2xl border-4 border-red-700 bg-red-50 space-y-3">
      <p className="text-xl font-bold text-red-900">⚠️ {msg}</p>
      <BigButton tone="red" icon="🔄" onClick={onRetry}>{t("ui.retry")}</BigButton>
    </div>
  );
}

export function Stepper({ value, onChange, min, max, step, unit }: { value: number; onChange: (v: number) => void; min: number; max: number; step: number; unit?: string }) {
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const b = "min-w-[72px] min-h-[72px] rounded-2xl text-4xl font-bold bg-gray-200 border-2 border-gray-600 active:bg-gray-300 disabled:opacity-40";
  return (
    <div className="flex items-center justify-between gap-3" dir="ltr">
      <button className={b} aria-label="minus" disabled={value <= min} onClick={() => onChange(clamp(value - step))}>−</button>
      <div className="text-center"><div className="text-5xl font-bold tabular-nums">{value}</div>{unit && <div className="text-lg">{unit}</div>}</div>
      <button className={b} aria-label="plus" disabled={value >= max} onClick={() => onChange(clamp(value + step))}>+</button>
    </div>
  );
}

/** Big mic. Falls back to a text box when listening isn't possible. onText receives what was said/typed. */
export function MicInput({ onText, placeholder, busy }: { onText: (s: string) => void; placeholder?: string; busy?: boolean }) {
  const { t, bcp47, lang } = useI18n();
  const [l, setL] = useState<Listener | null>(null);
  const [typing, setTyping] = useState(!canListen());
  const [txt, setTxt] = useState("");
  const [err, setErr] = useState("");
  const start = async () => {
    setErr("");
    try {
      const li = await listen(bcp47, lang); setL(li);
      li.result.then((s) => { setL(null); onText(s); }).catch(() => { setL(null); setErr(t("ui.post.degraded")); setTyping(true); });
    } catch { setTyping(true); setErr(t("ui.post.no_voice")); }
  };
  return (
    <div className="space-y-3">
      {!typing || l ? (
        <button onClick={l ? () => l.stop() : start} disabled={busy} aria-label={t("ui.post.tap")}
          className={`mx-auto flex flex-col items-center justify-center w-44 h-44 rounded-full text-7xl text-white shadow-lg ${l ? "bg-red-700 animate-pulse" : "bg-green-700 active:bg-green-900"}`}>
          <span aria-hidden>🎤</span><span className="text-lg mt-1">{l ? t("ui.post.listening") : t("ui.post.tap")}</span>
        </button>
      ) : null}
      {err && <p role="alert" className="text-center text-red-800 font-bold">{err}</p>}
      {typing ? (
        <div className="space-y-2">
          <textarea value={txt} onChange={(e) => setTxt(e.target.value)} placeholder={placeholder || t("ui.post.type_ph")} rows={3}
            className="w-full rounded-2xl border-4 border-gray-600 p-3 text-xl" />
          <BigButton disabled={!txt.trim() || busy} onClick={() => { onText(txt); setTxt(""); }}>{t("ui.post.send")}</BigButton>
        </div>
      ) : <button className="block mx-auto underline text-lg min-h-[56px]" onClick={() => setTyping(true)}>⌨️ {t("ui.post.type")}</button>}
    </div>
  );
}

export function TabBar({ tabs }: { tabs: { to: string; icon: string; label: string }[] }) {
  return (
    <nav className="fixed bottom-0 inset-x-0 bg-white border-t-4 border-brand grid z-20" style={{ gridTemplateColumns: `repeat(${tabs.length},1fr)` }}>
      {tabs.map((tb) => (
        <NavLink key={tb.to} to={tb.to} end className={({ isActive }) => `min-h-[72px] flex flex-col items-center justify-center text-lg font-bold ${isActive ? "bg-brand text-white" : "text-black"}`}>
          <span className="text-3xl" aria-hidden>{tb.icon}</span>{tb.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function useAsync<T>(fn: () => Promise<T>, deps: any[] = [], live = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const ref = useRef(fn); ref.current = fn;
  const version = useRef(0);
  const run = async (quiet = false) => {
    const id = ++version.current;
    if (!quiet) setLoading(true);
    try { const next = await ref.current(); if (id === version.current) {setData(next); setError(null);} }
    catch (e) { if (id === version.current) setError(e); }
    finally { if (id === version.current) setLoading(false); }
  };
  useEffect(() => {
    run();
    const refresh = () => { if (!document.hidden) run(true); };
    const timer = live ? setInterval(refresh, 5000) : undefined;
    if (live) window.addEventListener("focus",refresh);
    return () => { ++version.current; clearInterval(timer); window.removeEventListener("focus",refresh); };
  }, [...deps,live]);
  return { data, error, loading, reload: run, setData };
}

export const money = (n: number, sym: string) => `${sym} ${n.toLocaleString("en-US")}`;
export const pct = (x: number | null | undefined) => (x == null ? null : `${Math.round(x * 100)}%`);
