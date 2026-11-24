import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { useI18n } from "../i18n";
import { useSession } from "../session";
import { WorkMap, type Point, type MarketJob } from "../components/WorkMap";
import type { WorkLocation } from "../components/useWorkLocation";
import { AreaSearch } from "../components/AreaSearch";
import { RequestForm } from "../components/RequestForm";
import { PushControl } from "../components/PushControl";
import { SpeakerButton } from "../components/ui";
import { Icon } from "../components/Icon";
import { ReportLink } from "./Worker";
import { Login } from "./Onboarding";
import { DemoEntry, DemoSwitch } from "../components/Demo";
import { TradeIcon } from "../components/TradeIcon";
import { FreeToggle, Invites } from "./Daily";

const preview: Point = {lat:33.6575, lon:72.959, name:"G-13"};
const noPlaces: Point[] = [];
type Booking = { job: MarketJob; agreement_id: string };
type Agreement = { terms: {lat: number; lon: number; address_detail?: string}; hirer: {phone: string; first_name: string} };

function distance(a: Point, b: Point) {
  return Math.hypot((a.lat-b.lat)*111, (a.lon-b.lon)*111*Math.cos(a.lat*Math.PI/180));
}

export function MapHome({ location }: { location: WorkLocation }) {
  const {me, country, role, setRole} = useSession();
  const {lang, setLang, t, bcp47} = useI18n();
  const worker = me?.role === "worker";
  const places = country?.places || noPlaces;
  const profile = me?.profile;
  const base = useMemo(() => profile?.lat != null && profile.lon != null
    ? {lat: profile.lat, lon: profile.lon, name: profile.area_name}
    : places[0] || preview, [places, profile]);
  const point = location.point || base;
  const located = Boolean(location.point || profile?.lat != null);
  const nearest = places.reduce<Point | undefined>((best,p) => !best || distance(p,point)<distance(best,point) ? p : best, undefined);
  const area = point.name || (nearest && distance(nearest,point)<3 ? nearest.name : undefined) || t("map.pinned");
  const [rows,setRows] = useState<MarketJob[]>([]);
  const [selected,setSelected] = useState("");
  const [compose,setCompose] = useState(false);
  const [search,setSearch] = useState(false);
  const [expanded,setExpanded] = useState(false);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [booking,setBooking] = useState(false);
  const [receipt,setReceipt] = useState<Booking | null>(null);
  const [agreement,setAgreement] = useState<Agreement | null>(null);
  const [contactError,setContactError] = useState(false);
  const [contactRetry,setContactRetry] = useState(0);
  const [revision,setRevision] = useState(0);
  const sheet = useRef<HTMLDivElement>(null);
  const [myTier,setMyTier] = useState<{icon:string}|null>(null);
  useEffect(() => { if (!worker || !me) return; let live = true;
    api<{tier:{icon:string}}>("/reputation/"+me.id).then(r=>{if(live)setMyTier(r.tier);}).catch(()=>{}); return () => {live=false;}; }, [worker, me?.id]);
  const radius = profile?.radius_km || country?.default_radius_km || 10;
  const query = worker ? (located ? "/jobs/nearby?all_trades=true&lat="+point.lat+"&lon="+point.lon : "") : "/jobs/mine";
  const job = receipt?.job || rows.find(j => j.id===selected);
  const symbol = country?.currency.symbol || job?.currency || "";
  const openJobs = useMemo(() => rows.filter(j => !j.booking_expired && ["open","offers","assigned"].includes(j.status) && j.booked<j.headcount), [rows]);
  const mapJobs = useMemo(() => {
    if (!job) return openJobs;
    const pin = agreement && receipt ? {...job, lat:agreement.terms.lat, lon:agreement.terms.lon} : job;
    return [...openJobs.filter(j => j.id!==job.id), pin];
  }, [openJobs,job,receipt,agreement]);

  useEffect(() => {
    if (!me || !query) {setRows([]); setLoading(false); return;}
    let live = true, pending = false;
    setLoading(true);
    async function refresh() {
      if (pending || document.hidden) return;
      pending=true;
      try {
        const jobs = await api<MarketJob[]>(query);
        if (live) {setRows(jobs); setError("");}
      } catch {if (live) setError("ui.error.network");}
      finally {pending=false; if(live) setLoading(false);}
    }
    refresh();
    const timer = setInterval(refresh, 5000);
    document.addEventListener("visibilitychange",refresh);
    return () => {live=false; clearInterval(timer); document.removeEventListener("visibilitychange",refresh);};
  }, [query,me?.id,revision]);
  useEffect(() => {
    if (!receipt) {setAgreement(null); return;}
    let live = true;
    setContactError(false); setAgreement(null);
    api<Agreement>("/agreements/"+receipt.agreement_id).then(data => {if(live)setAgreement(data);})
      .catch(() => {if(live)setContactError(true);});
    return () => {live=false;};
  }, [receipt,contactRetry]);
  useEffect(() => {sheet.current?.scrollTo({top:0});}, [selected,compose,role]);

  function select(id: string) {
    setReceipt(null); setAgreement(null); setSelected(id); setCompose(false); setSearch(false); setNotice(""); setExpanded(true);
  }
  function choose(p: Point) {
    if (worker) setRows([]);
    location.choose(p); setSearch(false);
    if (!compose) {select(""); setExpanded(false);}
  }
  function posted(j: MarketJob) {
    setRows(prev => [j,...prev.filter(x=>x.id!==j.id)]); select(j.id);
    setNotice("market.published"); setRevision(n=>n+1);
  }
  async function book(j: MarketJob) {
    if(booking) return;
    setBooking(true); setNotice("");
    try {
      const result = await api<{agreement_id:string}>("/jobs/"+j.id+"/book", {method:"POST", retries:0});
      setReceipt({job:j, agreement_id:result.agreement_id}); setRevision(n=>n+1);
    } catch(e) {
      if((e as ApiError).status===409) {setSelected(""); setNotice("map.unavailable"); setRevision(n=>n+1);}
      else setNotice("ui.error.network");
    } finally {setBooking(false);}
  }
  const title = (j: MarketJob) => country?.trades.find(tr=>tr.code===j.task)?.names[lang] || j.task_name;
  const time = (j: MarketJob) => new Date(j.start_at).toLocaleString(bcp47,{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  const back = () => {select(""); setExpanded(false);};
  function openInvite(id: string) {
    const known = rows.find(j=>j.id===id);
    if (known) {select(id); return;}
    api<MarketJob>("/jobs/"+id).then(j=>{setRows(prev=>[j,...prev.filter(x=>x.id!==j.id)]); select(j.id);}).catch(()=>setNotice("map.unavailable"));
  }
  return <main className={"market"+(!me?" guest-market":"")+(expanded?" expanded":"")}>
    <header className="market-head"><div className="wordmark" dir="ltr"><span className="brand-mark" aria-hidden="true">d</span>Dihari</div>
      <div className="head-actions"><DemoSwitch/>
      {worker && <Link aria-label={t("ui.tab.me")} to="/me">{myTier ? <span aria-hidden="true">{myTier.icon}</span> : <Icon name="user"/>}</Link>}
      <button className="lang-btn" onClick={()=>setLang(lang==="ur"?"en":"ur")}>{lang==="ur"?"English":"اردو"}</button>
      {!me && <SpeakerButton text={t("market.welcome")+". "+t("market.intro")}/>}</div></header>
    <div className="market-layout">
      <WorkMap point={point} choose={choose} jobs={mapJobs} places={places} selectJob={select} locate={location.locate}
        locating={location.status==="locating"} worker={worker} selected={selected} currency={symbol} showPoint={located}/>
      <aside className="market-sheet">
        <button className="sheet-grip" aria-label={t(expanded?"market.moreMap":"market.moreSheet")} aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}><i/></button>
        <div className="sheet-scroll" ref={sheet}>
        {!me ? <section key={role || "welcome"} className="sheet-enter entry">
          <span className="eyebrow"><i/>{t("market.exchange")}</span>
          {role ? <Login/> : <><h1>{t("market.welcome")}</h1><p className="muted">{t("market.intro")}</p><DemoEntry/>
          <div className="role-list">{(["worker","hirer"] as const).map(r=>
            <button key={r} onClick={()=>setRole(r)}><span className="role-icon"><Icon name={r==="worker"?"work":"hire"} size={24}/></span>
            <span><strong>{t("market."+r)}</strong><small>{t("market."+r+"Hint")}</small></span><Icon name="arrow"/></button>)}</div></>}
        </section> : <>
          <div className="area-row"><span className="area-icon"><Icon name="pin"/></span><div><small>{t(location.status==="device"?"market.device":"map.area")}</small><strong>{located ? area : t("market.chooseArea")}</strong></div>
            <button className="icon-button" aria-expanded={search} aria-label={t("map.search")} onClick={()=>setSearch(!search)}><Icon name="search"/></button></div>
          {(search || !located) && <div className="area-panel sheet-enter">
            <AreaSearch places={places} point={point} choose={choose}/>
            {!located && <>{location.status==="locating" ? <small role="status">{t("map.locating")}</small> : <small>{t("map.manual")}</small>}
              <div className="chips">{places.slice(0,3).map(p=><button key={p.name} onClick={()=>choose(p)}>{p.name}</button>)}</div></>}
          </div>}
          {error && <p className="notice" role="alert">{t(error)} <button className="text-button" onClick={()=>setRevision(n=>n+1)}>{t("ui.retry")}</button></p>}
          {notice && <p className="notice" role="status">{t(notice)}</p>}
          {compose ? <section key="compose" className="sheet-enter"><button className="back-link" onClick={back}><Icon name="back"/>{t("ui.back")}</button>
            {located && <RequestForm point={point} area={area} onPosted={posted}/>}</section> :
          job ? <section key={job.id} className="sheet-enter details">
            <button className="back-link" onClick={back}><Icon name="back"/>{t(worker?"ui.jobs.title":"ui.tab.myjobs")}</button>
            <span className="eyebrow"><i/>{t(receipt?"market.confirmed":worker?"market.jobDetails":"market.yourRequest")}</span>
            <h1>{title(job)}</h1>{job.urgent && <span className="pill urgent-badge">⚡ {t("urgent.badge")}</span>}{worker && job.hirer_reputation?.pays_on_time_badge && <span className="pays-badge">✅ {t("hirer.pays_badge")}</span>}<div className="pay-line"><strong>{symbol} {job.daily_rate.toLocaleString(bcp47)}</strong> {t("market.perDay")}</div>
            <div className="facts"><span><Icon name="pin"/>{job.location_text}</span><span><Icon name="clock"/>{time(job)} · {t("ui.job.hours",{h:job.hours_per_day})}</span>
            <span><Icon name="work"/>{t(receipt?"market.bookedByYou":worker?"map.spots":"map.booked", {n:worker ? job.headcount-job.booked : job.booked,total:job.headcount})}</span></div>
            {receipt ? <div className="contact-panel">
              <h2>{t("market.contact")}</h2>{agreement ? <><p>{agreement.hirer.first_name} {agreement.terms.address_detail && "· "+agreement.terms.address_detail}</p>
                <a className="primary" href={"tel:"+agreement.hirer.phone}>{t("market.call")} <bdi>{agreement.hirer.phone}</bdi></a>
                <a className="secondary" href={"https://www.google.com/maps/dir/?api=1&destination="+agreement.terms.lat+","+agreement.terms.lon} target="_blank" rel="noreferrer">{t("map.directions")}</a></>
                : contactError ? <button onClick={()=>setContactRetry(n=>n+1)}>{t("ui.retry")}</button> : <p role="status">{t("market.loading")}</p>}</div>
            : worker ? <><div className="terms"><p>{t("map.payDay")} · {job.payment_day}</p><p>{t("map.days")} · {job.days}　{t("map.advance")} · {job.advance}</p>
              <p>{t("map.transport")} · {t("readback.transport."+job.transport_mode,{amount:job.transport_amount||0,currency:job.currency})}</p>
              {job.deductions.map((d,i)=><p key={i}>{d.label} − {d.amount}</p>)}
              {!job.rule_verified && <small>{t("ui.job.unverified")}</small>}</div>
              {job.my_assignment_id ? <Link className="primary" to="/work">{t("ui.tab.mywork")}</Link> : <>
              <button disabled={booking} className="primary" onClick={()=>book(job)}>{t("market.accept")}</button>
              <Link className="secondary" to={"/counter/"+job.id}>{t("ui.counter")}</Link></>}
              <div className="detail-tools"><SpeakerButton load={async()=>(await api("/jobs/"+job.id+"/readback")).text}/><ReportLink id={job.id}/></div></>
            : <Link className="primary" to={"/jobs-mine/"+job.id}>{t("market.manage")}</Link>}
          </section> : <section key="feed" className="sheet-enter">
            <div className="feed-heading"><div><span className="eyebrow"><i/>{t(worker?"market.workerView":"market.hirerView")}</span>
              <h1>{t(worker?"market.openJobs":"market.requests")}</h1></div>{worker && located && <span className="radius">{radius} km</span>}</div>
            {worker && <div className="feed-extras"><FreeToggle/><Invites onOpen={openInvite}/></div>}
            {!worker && <button className="primary post-action" onClick={()=>{setCompose(true); setExpanded(true);setNotice("");}} disabled={!located}><Icon name="plus"/>{t("map.request")}</button>}
            {loading ? <p role="status" className="muted">{t("market.loading")}</p> : !error && (worker?openJobs:rows).length===0 && (located || !worker) && <div className="empty"><Icon name={worker?"map":"work"} size={28}/><h2>{t(worker?"ui.jobs.empty":"market.noRequests")}</h2><p>{t(worker?"market.tryArea":"market.postHint")}</p></div>}
            <div className="job-list">{(worker?openJobs:rows).map(j=><button key={j.id} className={"job-row"+(j.urgent?" urgent":"")} onClick={()=>select(j.id)}>
              <span className="row-title"><strong><span className="trade-icon" aria-hidden="true"><TradeIcon code={j.task}/></span>{title(j)}</strong><b>{symbol} {j.daily_rate.toLocaleString(bcp47)}</b></span>
              {(j.urgent || j.invited) && <span className="flex gap-2">{j.urgent && <span className="pill urgent-badge">⚡ {t("urgent.badge")}</span>}{j.invited && <span className="pill gold">📣 {t("inv.title")}</span>}</span>}
              <span className="row-sub">{j.location_text}{worker && " · "+t("ui.job.km",{km:j.distance_km||0})}</span>
              <span className="row-foot"><span>{time(j)}</span><em>{worker ? t("map.spots",{n:j.headcount-j.booked}) : j.booking_expired ? t("map.expired") : t("map.booked",{n:j.booked,total:j.headcount})}</em></span></button>)}</div>
            <PushControl/></section>}
        </>}</div>
      </aside></div></main>;
}
