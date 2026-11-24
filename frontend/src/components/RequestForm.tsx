import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { MicInput } from "./ui";
import type { Point, MarketJob } from "./WorkMap";

function localDate(d: Date) {
  return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);
}

export function RequestForm({point, area, onPosted}: {point: Point; area: string; onPosted: (job: MarketJob) => void}) {
  const {country} = useSession();
  const {t,lang} = useI18n();
  const [voice,setVoice] = useState(false);
  const [task,setTask] = useState("");
  const [count,setCount] = useState(1);
  const [rate,setRate] = useState("");
  const [hours,setHours] = useState(8);
  const [start,setStart] = useState(() => localDate(new Date(Date.now()+3600000)));
  const [payDate,setPayDate] = useState("");
  const [landmark,setLandmark] = useState("");
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  async function fill(text: string) {
    setBusy(true); setError("");
    try {
      const {fields} = await api("/voice/draft",{method:"POST",body:{transcript:text,lang}});
      if (fields.task) setTask(fields.task);
      if (fields.headcount) setCount(fields.headcount);
      if (fields.daily_rate) setRate(String(fields.daily_rate));
      if (fields.hours_per_day) setHours(fields.hours_per_day);
      if (fields.start_at) setStart(localDate(new Date(fields.start_at)));
      if (fields.payment_day) setPayDate(fields.payment_day);
      setVoice(false);
    } catch {setError(t("ui.error.network"));}
    finally {setBusy(false);}
  }
  async function submit() {
    setBusy(true); setError("");
    try {
      const job = await api<MarketJob>("/jobs",{method:"POST", retries:0, body:{task,headcount:count,location_text:area,
        address_detail:landmark,lat:point.lat,lon:point.lon,start_at:new Date(start).toISOString(),
        daily_rate:Number(rate),hours_per_day:hours,payment_day:payDate || start.slice(0,10)}});
      onPosted(job);
    } catch(e) {
      const a = e as ApiError;
      setError(a.detail?.detail?.violations?.map((v:{message:string})=>v.message).join(" ") ||
        (a.code==="duplicate" ? t("map.duplicate") : t("ui.error.generic")));
    } finally {setBusy(false);}
  }
  return <><div className="sheet-title"><h2>{t("map.request")}</h2><button className="text-button" onClick={()=>setVoice(!voice)}>{t("map.voice")}</button></div>
    {voice && <MicInput busy={busy} onText={fill}/>}
    <form className="request-fields" onSubmit={e=>{e.preventDefault();submit();}}>
      <label>{t("map.trade")}<select required value={task} onChange={e=>setTask(e.target.value)}><option value="">—</option>{country?.trades.map(tr=><option key={tr.code} value={tr.code}>{tr.names[lang]||tr.names.en}</option>)}</select></label>
      <label>{t("map.workers")}<input type="number" min="1" max="200" required value={count || ""} onChange={e=>setCount(Number(e.target.value))}/></label>
      <label className="wide">{t("map.landmark")}<input value={landmark} onChange={e=>setLandmark(e.target.value)} maxLength={250}/></label>
      <label>{t("map.rate")} ({country?.currency.symbol})<input required inputMode="numeric" type="number" min="1" value={rate} onChange={e=>setRate(e.target.value)}/></label>
      <label>{t("map.hours")}<input required type="number" min="1" max="24" value={hours||""} onChange={e=>setHours(Number(e.target.value))}/></label>
      <label className="wide">{t("map.start")}<input required type="datetime-local" min={localDate(new Date())} value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label className="wide">{t("map.payDay")}<input type="date" required min={start.slice(0,10)} value={payDate || start.slice(0,10)} onChange={e=>setPayDate(e.target.value)}/></label>
      {error && <p className="wide error" role="alert">{error}</p>}
      <small className="wide">{t("ui.job.unverified")}</small>
      <button disabled={busy} className="primary wide">{t("map.publish")}</button>
    </form><Link className="text-button" to="/post/assisted">{t("map.assisted")}</Link></>;
}
