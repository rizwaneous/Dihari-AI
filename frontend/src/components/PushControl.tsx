import {useEffect, useState} from "react";
import {api} from "../api";
import {useI18n} from "../i18n";

export async function disablePush() {
  const registration = await navigator.serviceWorker?.getRegistration();
  const sub = await registration?.pushManager?.getSubscription();
  if (!sub) return;
  await sub.unsubscribe();
  await api("/notifications/unsubscribe", {method:"POST", body:{endpoint:sub.endpoint}});
}

export function PushControl() {
  const {t} = useI18n();
  const [key,setKey] = useState("");
  const [enabled,setEnabled] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState(false);
  useEffect(()=>{
    if (!("PushManager" in window)) return;
    navigator.serviceWorker.getRegistration().then(async reg=>{
      if (!reg?.active) return;
      const config=await api("/notifications/config");
      setKey(config.public_key);
      setEnabled(!!await reg.pushManager.getSubscription());
    }).catch(()=>{});
  },[]);
  if(!key) return null;
  async function toggle() {
    setBusy(true);setError(false);
    try {
      if(enabled) {await disablePush();setEnabled(false);}
      else {
        const permission=await Notification.requestPermission();
        if(permission!=="granted")throw Error();
        const bytes=Uint8Array.from(atob(key.replace(/-/g,"+").replace(/_/g,"/")),c=>c.charCodeAt(0));
        const reg=await navigator.serviceWorker.ready;
        const sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes});
        try {await api("/notifications/subscribe",{method:"POST",body:sub.toJSON()});}
        catch(e){await sub.unsubscribe();throw e;}
        setEnabled(true);
      }
    } catch {setError(true);} finally {setBusy(false);}
  }
  return <div><button className="text-button" disabled={busy} onClick={toggle}>{t(enabled?"map.alertOff":"map.alertOn")}</button>{error && <p role="alert">{t("ui.error.generic")}</p>}</div>;
}
