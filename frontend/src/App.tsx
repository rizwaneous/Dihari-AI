import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Skeleton } from "./components/ui";
import { useI18n } from "./i18n";
import { useWorkLocation } from "./components/useWorkLocation";
import { AppShell } from "./components/Shell";
import PostJob from "./pages/PostJob";
import { MapHome } from "./pages/MapHome";
import { JobDetail, MyJobs } from "./pages/Hirer";
import { Counter, MyWork } from "./pages/Worker";
import { KaamCard } from "./pages/KaamCard";
import { FreeWorkers, HelpPage, PublicCard, TeamPage } from "./pages/Daily";
import { useSession } from "./session";
import { useEffect, useState } from "react";

function OfflineBanner() {
  const { t } = useI18n();
  const [off, setOff] = useState(!navigator.onLine);
  useEffect(() => { const a = () => setOff(true), b = () => setOff(false); window.addEventListener("offline", a); window.addEventListener("online", b); return () => { window.removeEventListener("offline", a); window.removeEventListener("online", b); }; }, []);
  return off ? <p role="status" className="bg-yellow-300 text-black text-center font-bold p-2">{t("ui.offline")}</p> : null;
}

export default function App() {
  const { ready } = useI18n();
  const { me, loading } = useSession();
  const location = useWorkLocation();
  const route = useLocation();
  if (!ready || loading) return <Skeleton />;
  // The shared Kaam Card link works for anyone, logged in or not.
  if (route.pathname.startsWith("/card/")) return <Routes><Route path="/card/:token" element={<PublicCard />} /></Routes>;
  if (!me) return <MapHome key="guest" location={location} />;
  return (
    <AppShell>
      <OfflineBanner />
      {me.role === "hirer" ? (
        <Routes>
          <Route path="/" element={<MapHome key={me.id} location={location} />} />
          <Route path="/post/assisted" element={<PostJob />} />
          <Route path="/jobs-mine" element={<MyJobs />} />
          <Route path="/jobs-mine/:id" element={<JobDetail />} />
          <Route path="/workers" element={<FreeWorkers location={location} />} />
          <Route path="/team" element={<TeamPage />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      ) : (
        <Routes>
          <Route path="/" element={<MapHome key={me.id} location={location} />} />
          <Route path="/counter/:id" element={<Counter />} />
          <Route path="/work" element={<MyWork />} />
          <Route path="/me" element={<KaamCard />} />
          <Route path="/help" element={<HelpPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      )}
    </AppShell>
  );
}
