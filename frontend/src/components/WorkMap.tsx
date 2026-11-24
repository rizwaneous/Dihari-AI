import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Icon } from "./Icon";
import { useI18n } from "../i18n";

export type Point = { lat: number; lon: number; name?: string };
export type MapJob = Point & { id: string; daily_rate: number; task_name: string };

export type MarketJob = MapJob & {
  task: string; currency: string; status: string; location_text: string; booking_expired: boolean;
  start_at: string; days: number; hours_per_day: number; headcount: number; booked: number;
  distance_km?: number; payment_day: string; rule_verified: boolean; advance: number;
  deductions: {label: string; amount: number}[]; transport_mode: string; transport_amount?: number;
  my_assignment_id?: string; urgent?: boolean; invited?: boolean; my_offer?: {status: string; rate: number};
  hirer_reputation?: {pays_on_time_badge?: boolean; on_time_payment_rate?: number | null};
};
export function WorkMap({ point, jobs, places, choose, selectJob, locate, locating, worker, selected, currency, showPoint }: {
  point: Point; jobs: MapJob[]; places: Point[]; choose: (p: Point) => void;
  selectJob: (id: string) => void; locate: () => void; locating: boolean; worker: boolean; selected?: string; currency?: string; showPoint: boolean;
}) {
  const { t } = useI18n();
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const rateMarkers = useRef(new Map<string, {marker: L.Marker; label: HTMLSpanElement}>());
  const actions = useRef({ choose, selectJob });
  actions.current = { choose, selectJob };
  const [moved, setMoved] = useState(false);
  const [tilesFailed, setTilesFailed] = useState(false);
  useEffect(() => {
    const m = L.map(container.current!, { zoomControl: false }).setView([point.lat, point.lon], 13);
    map.current = m;
    L.tileLayer(import.meta.env.VITE_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).on("tileerror", () => setTilesFailed(true)).on("tileload", () => setTilesFailed(false)).addTo(m);
    L.control.zoom({ position: "bottomleft" }).addTo(m);
    m.on("dragend", () => setMoved(true));
    m.on("click", (e: L.LeafletMouseEvent) => actions.current.choose({ lat: e.latlng.lat, lon: e.latlng.lng }));
    const observer = new ResizeObserver(() => m.invalidateSize());
    observer.observe(container.current!);
    return () => { observer.disconnect(); rateMarkers.current.clear(); m.remove(); map.current = null; };
  }, []);
  useEffect(() => {
    const m = map.current!;
    m.setView([point.lat, point.lon], m.getZoom());
    setMoved(false);
    if (!showPoint) return;
    const marker = L.marker([point.lat, point.lon], { interactive: false,
      icon: L.divIcon({ className: "work-pin", html: "<i></i>", iconSize: [20, 20], iconAnchor: [10, 10] }) }).addTo(m);
    return () => { marker.remove(); };
  }, [point, showPoint]);
  useEffect(() => {
    const markers = rateMarkers.current;
    const ids = new Set(jobs.map(j => j.id));
    for (const [id, entry] of markers) {
      if (!ids.has(id)) {entry.marker.remove(); markers.delete(id);}
    }
    for (const job of jobs) {
      let entry = markers.get(job.id);
      if (!entry) {
        const label = document.createElement("span");
        const icon = L.divIcon({className:"rate-pin", html:label, iconSize:[68,32], iconAnchor:[34,32]});
        const marker = L.marker([job.lat,job.lon], {icon,title:job.task_name,alt:job.task_name})
          .on("click", () => actions.current.selectJob(job.id)).addTo(map.current!);
        entry = {marker,label};
        markers.set(job.id,entry);
      }
      entry.label.textContent = [currency,job.daily_rate].filter(Boolean).join(" ");
      const pos = entry.marker.getLatLng();
      if (pos.lat !== job.lat || pos.lng !== job.lon) entry.marker.setLatLng([job.lat,job.lon]);
      entry.marker.getElement()?.classList.toggle("selected-pin", job.id===selected);
      entry.marker.setZIndexOffset(job.id===selected ? 800 : 0);
    }
  }, [jobs, selected, currency]);
  useEffect(() => {
    const markers = L.layerGroup().addTo(map.current!);
    if (tilesFailed) places.forEach(place => {
      const label = document.createElement("span"); label.textContent = place.name || "";
      L.circleMarker([place.lat, place.lon], {radius: 3, color: "#50796b"}).bindTooltip(label, {permanent:true})
        .on("click", () => actions.current.choose(place)).addTo(markers);
    });
    return () => { markers.remove(); };
  }, [places, tilesFailed]);
  const active = jobs.find(j => j.id === selected);
  useEffect(() => {
    if (active) map.current?.panTo([active.lat, active.lon], {animate: !window.matchMedia("(prefers-reduced-motion: reduce)").matches, duration: 0.25});
  }, [active?.id, active?.lat, active?.lon]);
  return <section className="map-space" aria-label={t("map.area")}>
    <div ref={container} className="map-canvas" dir="ltr"/>
    <button className="locate" onClick={locate} disabled={locating}><Icon name="target" size={18}/>{t(locating ? "map.locating" : "map.locate")}</button>
    {tilesFailed && <span className="tile-error" role="status">{t("map.tiles")}</span>}
    {moved && <button className="use-center" onClick={() => { const p = map.current!.getCenter(); choose({lat:p.lat,lon:p.lng}); }}>{t(worker ? "map.searchHere" : "map.pinHere")}</button>}
  </section>;
}
