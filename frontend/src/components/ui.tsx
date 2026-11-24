import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api";
import { useI18n } from "../i18n";
import { canListen, listen, speak, stopSpeaking, type Listener } from "../voice";
import { DemoSwitch } from "./Demo";
import { Icon } from "./Icon";

type Tone = "green" | "red" | "gray" | "blue" | "gold";

export function BigButton({ tone = "green", icon, children, onClick, disabled, className = "", small }: { tone?: Tone; icon?: ReactNode; children: ReactNode; onClick?: () => void; disabled?: boolean; className?: string; small?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled} className={`btn btn-${tone}${small ? " btn-sm" : ""} ${className}`}>
      {icon && <span aria-hidden className="ico">{icon}</span>}<span>{children}</span>
    </button>
  );
}

/** Auto-voice: every screen reads itself aloud on open unless the person turned it off. */
export const autoVoiceOn = () => { try { return localStorage.getItem("autoVoice") !== "off"; } catch { return true; } };
export const setAutoVoice = (on: boolean) => { try { localStorage.setItem("autoVoice", on ? "on" : "off"); } catch { /* */ } };

export function SpeakerButton({ text, load, auto }: { text?: string; load?: () => Promise<string>; auto?: boolean }) {
  const { t, bcp47, lang } = useI18n();
  const [on, setOn] = useState(false);
  const play = async () => {
    setOn(true);
    try { const s = load ? await load() : text || ""; if (s) await speak(s, bcp47, lang); } catch { /* visual fallback remains */ }
    setTimeout(() => setOn(false), 1200);
  };
  useEffect(() => { if (auto && autoVoiceOn() && (text || load)) play(); return () => stopSpeaking(); /* eslint-disable-next-line */ }, [text, auto]);
  return (
    <button aria-label={t("ui.speak")} title={t("ui.speak")} onClick={on ? () => { stopSpeaking(); setOn(false); } : play} className={`speaker${on ? " on" : ""}`}>
      <span aria-hidden>🔊</span>
    </button>
  );
}

export function ScreenHeader({ title, speakText, auto, back }: { title: string; speakText: string; auto?: boolean; back?: string }) {
  const { t } = useI18n();
  return (
    <header className="screen-head">
      {back && <Link to={back} className="back" aria-label={t("ui.back")}><Icon name="back" size={22} /></Link>}
      <h1>{title}</h1>
      <div className="head-tools"><DemoSwitch /><SpeakerButton text={speakText || title} auto={auto ?? true} /></div>
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
    <div role="alert" className="card warn">
      <p className="text-xl font-bold text-red-900">⚠️ {msg}</p>
      <BigButton tone="red" icon="🔄" onClick={onRetry}>{t("ui.retry")}</BigButton>
    </div>
  );
}

export function Stepper({ value, onChange, min, max, step, unit }: { value: number; onChange: (v: number) => void; min: number; max: number; step: number; unit?: string }) {
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  return (
    <div className="stepper" dir="ltr">
      <button aria-label="minus" disabled={value <= min} onClick={() => onChange(clamp(value - step))}>−</button>
      <div className="val"><b>{value.toLocaleString("en-US")}</b>{unit && <span>{unit}</span>}</div>
      <button aria-label="plus" disabled={value >= max} onClick={() => onChange(clamp(value + step))}>+</button>
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
          className={`mic${l ? " on" : ""}`}>
          <span aria-hidden>🎤</span><small>{l ? t("ui.post.listening") : t("ui.post.tap")}</small>
        </button>
      ) : null}
      {err && <p role="alert" className="text-center text-red-800 font-bold">{err}</p>}
      {typing ? (
        <div className="space-y-2">
          <textarea value={txt} onChange={(e) => setTxt(e.target.value)} placeholder={placeholder || t("ui.post.type_ph")} rows={3}
            className="w-full rounded-2xl border-2 border-gray-400 p-3 text-xl" />
          <BigButton disabled={!txt.trim() || busy} onClick={() => { onText(txt); setTxt(""); }}>{t("ui.post.send")}</BigButton>
        </div>
      ) : <button className="link-btn" onClick={() => setTyping(true)}>⌨️ {t("ui.post.type")}</button>}
    </div>
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

/** Friendly sentence for an API error code (err.<code> in the locale files), else the generic one. */
export function errMsg(t: (k: string, p?: Record<string, string | number>) => string, e: unknown): string {
  const a = e as ApiError;
  if (a?.status === 0) return t("ui.error.network");
  const k = "err." + (a?.code || "x");
  const s = t(k);
  return s === k ? t("ui.error.generic") : s;
}
