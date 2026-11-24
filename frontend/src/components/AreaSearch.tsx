import { useState } from "react";
import type { Point } from "./WorkMap";
import { useI18n } from "../i18n";

export function AreaSearch({ places, point, choose }: { places: Point[]; point: Point; choose: (p: Point) => void }) {
  const { t } = useI18n();
  const [query,setQuery] = useState("");
  const [results,setResults] = useState<Point[]>([]);
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState("");
  async function search() {
    const q = query.trim();
    if (!q || busy) return;
    setMessage("");
    const local = places.filter(p => p.name?.toLowerCase().includes(q.toLowerCase()));
    if (local.length) { setResults(local); return; }
    setBusy(true);
    try {
      const url = new URL(import.meta.env.VITE_GEOCODER_URL || "https://photon.komoot.io/api/");
      url.search = new URLSearchParams({q,limit:"5",lat:point.lat.toFixed(1),lon:point.lon.toFixed(1)}).toString();
      const r = await fetch(url, {signal: AbortSignal.timeout(8000)});
      if (!r.ok) throw Error();
      const {features} = await r.json();
      const next = features.map((f: {geometry:{coordinates:number[]}; properties:{name:string;city?:string}}) =>
        ({lat:f.geometry.coordinates[1],lon:f.geometry.coordinates[0],name:[f.properties.name,f.properties.city].filter(Boolean).join(", ")}));
      setResults(next);
      if (!next.length) setMessage(t("map.noPlaces"));
    } catch { setMessage(t("map.searchError")); }
    finally { setBusy(false); }
  }
  return <div className="area-search"><form onSubmit={e=>{e.preventDefault();search();}}>
    <input aria-label={t("map.search")} placeholder={t("map.search")} value={query} onChange={e=>{setQuery(e.target.value);setResults([]);setMessage("");}} disabled={busy}/>
    <button disabled={busy || !query.trim()} aria-label={t("map.search")}>{busy ? "…" : "⌕"}</button></form>
    {results.length>0 && <div className="place-results">{results.map(p=><button key={p.lat+","+p.lon} onClick={()=>{choose(p);setResults([]);setQuery("");}}>{p.name}</button>)}</div>}
    {message && <small role="status">{message}</small>}</div>;
}
