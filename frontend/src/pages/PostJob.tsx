import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { BigButton, ErrorRetry, MicInput, ScreenHeader, SpeakerButton, Stepper } from "../components/ui";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { TradeIcon } from "../components/TradeIcon";

const VIOLATION_FIELD: Record<string, string> = { below_min_wage: "daily_rate", net_below_min_wage: "daily_rate", hours_exceed_max: "hours_per_day",
  missing_payment_day: "payment_day", payment_too_late: "payment_day", payment_before_start: "payment_day", hidden_deduction: "deductions" };

const pad = (n: number) => String(n).padStart(2, "0");
const isoDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function FieldAsker({ field, fields, onPatch }: { field: string; fields: any; onPatch: (p: any) => void }) {
  const { t, lang, bcp47 } = useI18n();
  const { country } = useSession();
  const [num, setNum] = useState<number>(() => ({ headcount: fields.headcount || 2, daily_rate: fields.daily_rate || 1500, hours_per_day: fields.hours_per_day || 8, advance: 0, deductions: 100, transport_mode: 200 } as any)[field] ?? 1);
  const [hour, setHour] = useState(8);
  const [day, setDay] = useState<0 | 1>(1);
  const cur = country?.currency.symbol || "";
  const chip = "chip !rounded-2xl min-h-[64px] text-xl flex items-center gap-2 justify-center";
  const startDate = fields.start_at ? new Date(fields.start_at) : new Date();
  switch (field) {
    case "task": return <div className="grid grid-cols-2 gap-3">{country?.trades.map((tr) => <button key={tr.code} className={chip + " !min-h-[96px] flex-col"} onClick={() => onPatch({ task: tr.code })}><TradeIcon code={tr.code} size={44} /> {tr.names[lang] || tr.names.en}</button>)}</div>;
    case "location_text": return <div className="flex flex-wrap gap-3">{country?.places.map((p) => <button key={p.name} className={chip} onClick={() => onPatch({ location_text: p.name })}>{p.name}</button>)}</div>;
    case "headcount": return <div className="space-y-4"><Stepper value={num} onChange={setNum} min={1} max={50} step={1} unit={t("ui.q.unit.workers")} /><BigButton onClick={() => onPatch({ headcount: num })}>{t("ui.ok")}</BigButton></div>;
    case "daily_rate": return <div className="space-y-4"><Stepper value={num} onChange={setNum} min={100} max={20000} step={country?.rate_step || 50} unit={`${cur} ${t("ui.q.unit.rate")}`} /><BigButton onClick={() => onPatch({ daily_rate: num })}>{t("ui.ok")}</BigButton></div>;
    case "hours_per_day": return <div className="space-y-4"><Stepper value={num} onChange={setNum} min={1} max={16} step={1} unit={t("ui.q.unit.hours")} /><BigButton onClick={() => onPatch({ hours_per_day: num })}>{t("ui.ok")}</BigButton></div>;
    case "start_at": return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3"><button className={`${chip} ${day === 0 ? "!bg-brand !text-white" : ""}`} onClick={() => setDay(0)}>{t("ui.q.today")}</button><button className={`${chip} ${day === 1 ? "!bg-brand !text-white" : ""}`} onClick={() => setDay(1)}>{t("ui.q.tomorrow")}</button></div>
        <p className="text-xl font-bold text-center">{t("ui.q.hour", { h: hour })}</p>
        <Stepper value={hour} onChange={setHour} min={5} max={20} step={1} />
        <BigButton onClick={() => { const d = new Date(); d.setDate(d.getDate() + day); d.setHours(hour, 0, 0, 0); onPatch({ start_at: d.toISOString() }); }}>{t("ui.ok")}</BigButton>
      </div>);
    case "payment_day": return (
      <div className="grid grid-cols-2 gap-3">
        <button className={chip} onClick={() => { const d = new Date(startDate); d.setDate(d.getDate() + (fields.days || 1) - 1); onPatch({ payment_day: isoDate(d) }); }}>{t("ui.q.same_day")}</button>
        {Array.from({ length: 7 }).map((_, i) => { const d = new Date(startDate); d.setDate(d.getDate() + (fields.days || 1) + i); return (
          <button key={i} className={chip} onClick={() => onPatch({ payment_day: isoDate(d) })}>{d.toLocaleDateString(bcp47, { weekday: "long", day: "numeric" })}</button>); })}
      </div>);
    case "deductions": return (
      <div className="space-y-4"><BigButton tone="green" onClick={() => onPatch({ deductions: [] })}>{t("ui.q.none")}</BigButton>
        <div className="border-t-4 pt-4 space-y-3"><Stepper value={num} onChange={setNum} min={50} max={5000} step={50} unit={cur} /><BigButton tone="gray" onClick={() => onPatch({ deductions: [{ label: "deduction", amount: num }] })}>{t("ui.ok")}</BigButton></div></div>);
    case "advance": return (
      <div className="space-y-4"><BigButton tone="green" onClick={() => onPatch({ advance: 0 })}>{t("ui.q.none")}</BigButton>
        <div className="border-t-4 pt-4 space-y-3"><Stepper value={num || 500} onChange={setNum} min={100} max={20000} step={100} unit={`${cur} ${t("ui.q.unit.advance")}`} /><BigButton tone="gray" onClick={() => onPatch({ advance: num || 500 })}>{t("ui.ok")}</BigButton></div></div>);
    case "transport_mode": return (
      <div className="space-y-4"><div className="grid grid-cols-2 gap-3"><button className={chip} onClick={() => onPatch({ transport_mode: "none", transport_amount: null })}>{t("ui.q.none")}</button><button className={chip} onClick={() => onPatch({ transport_mode: "provided", transport_amount: null })}>{t("ui.q.provided")}</button></div>
        <div className="border-t-4 pt-4 space-y-3"><Stepper value={num} onChange={setNum} min={50} max={5000} step={50} unit={cur} /><BigButton tone="gray" onClick={() => onPatch({ transport_mode: "allowance", transport_amount: num })}>{t("ui.ok")}</BigButton></div></div>);
    default: return null;
  }
}

export default function PostJob() {
  const { t, lang } = useI18n();
  const { country } = useSession();
  const nav = useNavigate();
  const [fields, setFields] = useState<any>({});
  const [draft, setDraft] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [retry, setRetry] = useState<(() => void) | null>(null);
  const [transcript, setTranscript] = useState("");
  // Arriving from the voice assistant ("2 mistri chahiye kal G-13 mein"): start the draft from what was said.
  const spoken = (useLocation().state as any)?.text as string | undefined;
  const used = useRef(false);
  useEffect(() => { if (spoken && !used.current) { used.current = true; onTranscript(spoken); } /* eslint-disable-next-line */ }, [spoken]);

  const run = (fn: () => Promise<any>) => {
    const go = async () => { setBusy(true); setErr(null); try { const d = await fn(); setDraft(d); setFields(d.fields); } catch (e) { setErr(e); } setBusy(false); };
    setRetry(() => go); go();
  };
  const onTranscript = (txt: string) => { setTranscript((x) => `${x} ${txt}`.trim()); run(() => api("/voice/draft", { method: "POST", body: { transcript: txt, fields, lang } })); };
  const onAnswer = (field: string, txt: string) => run(() => api("/voice/answer", { method: "POST", body: { field, transcript: txt, fields, lang } }));
  const onPatch = (p: any) => run(() => api("/voice/validate", { method: "POST", body: { fields: { ...fields, ...p }, lang } }));
  const violations: any[] = draft?.wage?.violations || [];
  const focus: string | undefined = draft?.next_question?.field || (violations[0] && VIOLATION_FIELD[violations[0].code]);

  const post = async () => {
    setBusy(true); setErr(null);
    try { const job = await api("/jobs", { method: "POST", body: { ...fields, transcript, readback_verified: draft?.verifier?.ok === true }, retries: 0 }); nav("/jobs-mine/"+job.id); }
    catch (e) { setErr(e); setRetry(() => post); }
    setBusy(false);
  };
  const confirmByVoice = async (txt: string) => { const r = await api<{ intent: string }>("/voice/intent", { method: "POST", body: { transcript: txt, lang } }); if (r.intent === "yes") post(); else if (r.intent === "no") reset(); };
  const reset = () => { setDraft(null); setFields({}); setTranscript(""); setErr(null); };

  const unverified = draft?.wage?.warnings?.some((w: any) => w.code === "unverified_rule");
  return (
    <div className="page">
      <ScreenHeader back="/" title={t("ui.post.title")} speakText={draft?.ready ? `${draft.readback} ${t("ui.post.confirm_q")}` : draft?.next_question?.prompt || t("ui.post.speak")} auto={!!draft} />
      {unverified && <p className="m-4 p-3 rounded-2xl bg-yellow-100 border-4 border-yellow-600 text-lg font-bold">⚠️ {t("ui.post.unverified")}</p>}
      {!!err && (err as ApiError).code === "wage_floor"
        ? <p role="alert" className="m-4 p-3 bg-red-50 border-4 border-red-700 rounded-2xl font-bold">{(err as ApiError).detail?.detail?.violations?.map((v: any) => v.message).join(" ")}</p>
        : !!err && <ErrorRetry error={err} onRetry={() => retry?.()} />}
      {draft?.degraded && <p className="m-4 text-lg font-bold">{t("ui.post.degraded")}</p>}

      {!draft ? (
        <div className="page-body"><p className="text-xl text-center">{t("ui.post.speak")}</p><MicInput busy={busy} onText={onTranscript} /></div>
      ) : draft.ready ? (
        <div className="page-body">
          <div className="card gold text-2xl font-bold">{draft.readback}</div>
          {draft.verifier && !draft.verifier.available && <p className="text-lg font-bold text-yellow-900">⚠️ {t("ui.post.verifier_warn")}</p>}
          {!draft.can_post ? <p className="text-xl font-bold text-red-800">{t("ui.post.blocked")}</p> : (
            <>
              <p className="text-xl font-bold text-center">{t("ui.post.confirm_q")}</p>
              <BigButton tone="green" icon="✔" disabled={busy} onClick={post}>{t("ui.yes")}</BigButton>
              <MicInput busy={busy} onText={confirmByVoice} placeholder={t("ui.yes")} />
            </>)}
          <BigButton tone="red" icon="✖" onClick={reset}>{t("ui.post.edit")}</BigButton>
        </div>
      ) : (
        <div className="page-body">
          {violations.length > 0 && (
            <div role="alert" className="p-4 rounded-2xl border-4 border-red-700 bg-red-50 space-y-3">
              <p className="text-xl font-bold text-red-900">⛔ {t("ui.post.blocked")}</p>
              {violations.map((v, i) => <p key={i} className="text-lg font-bold">{v.message}</p>)}
              {draft.fixes.map((f: any, i: number) => <BigButton key={i} tone="red" onClick={() => onPatch({ [f.field]: f.value })}>{f.field === "daily_rate" ? t("ui.post.fix_rate", { min: f.value }) : t("ui.post.fix_hours", { max: f.value })}</BigButton>)}
            </div>)}
          {focus && (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3"><p className="text-2xl font-bold">{t(`ask.${focus}`)}</p><SpeakerButton text={t(`ask.${focus}`)} auto /></div>
              <MicInput busy={busy} onText={(s) => onAnswer(focus, s)} />
              <FieldAsker key={focus + JSON.stringify(fields[focus] ?? "")} field={focus} fields={fields} onPatch={onPatch} />
            </div>)}
          <BigButton tone="gray" onClick={reset}>{t("ui.cancel")}</BigButton>
        </div>)}
    </div>
  );
}
