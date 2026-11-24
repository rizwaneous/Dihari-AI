import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Skeleton, TabBar } from "./components/ui";
import { useI18n } from "./i18n";
import { useWorkLocation } from "./components/useWorkLocation";
import PostJob from "./pages/PostJob";
import { MapHome } from "./pages/MapHome";
import { JobDetail, MyJobs } from "./pages/Hirer";
import { Counter, Me, MyWork } from "./pages/Worker";
import { useSession } from "./session";
import { useEffect, useState } from "react";

function OfflineBanner() {
  const { t } = useI18n();
  const [off, setOff] = useState(!navigator.onLine);
  useEffect(() => { const a = () => setOff(true), b = () => setOff(false); window.addEventListener("offline", a); window.addEventListener("online", b); return () => { window.removeEventListener("offline", a); window.removeEventListener("online", b); }; }, []);
  return off ? <p role="status" className="bg-yellow-300 text-black text-center font-bold p-2">{t("ui.offline")}</p> : null;
}

export default function App() {
  const { ready, t } = useI18n();
  const { me, loading } = useSession();
  const location = useWorkLocation();
  const route = useLocation();
  if (!ready || loading) return <Skeleton />;
  if (!me) return <MapHome key="guest" location={location} />;
  return (
    <>
      <OfflineBanner />
      {me.role === "hirer" ? (
        <>
          <Routes>
            <Route path="/" element={<MapHome key={me.id} location={location} />} />
            <Route path="/post/assisted" element={<PostJob />} />
            <Route path="/jobs-mine" element={<MyJobs />} />
            <Route path="/jobs-mine/:id" element={<JobDetail />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
          {route.pathname !== "/" && <TabBar tabs={[{ to: "/", icon: "◎", label: t("map.area") }, { to: "/jobs-mine", icon: "📋", label: t("ui.tab.myjobs") }]} />}
        </>
      ) : (
        <>
          <Routes>
            <Route path="/" element={<MapHome key={me.id} location={location} />} />
            <Route path="/counter/:id" element={<Counter />} />
            <Route path="/work" element={<MyWork />} />
            <Route path="/me" element={<Me />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
          {route.pathname !== "/" && <TabBar tabs={[{ to: "/", icon: "◎", label: t("map.area") }, { to: "/work", icon: "🛠️", label: t("ui.tab.mywork") }, { to: "/me", icon: "👤", label: t("ui.tab.me") }]} />}
        </>
      )}
    </>
  );
}
