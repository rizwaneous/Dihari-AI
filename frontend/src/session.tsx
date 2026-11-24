import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { disablePush } from "./components/PushControl";
import { api, getToken, setToken } from "./api";

export interface Me { id: string; role: "worker" | "hirer"; name?: string; country: string; locale: string; profile?: any }
export interface Country { code: string; currency: { code: string; symbol: string }; trades: { code: string; icon: string; names: Record<string, string> }[]; places: { name: string; region: string; lat: number; lon: number }[]; rate_step: number; max_counter_multiple: number; default_radius_km: number; max_radius_km: number; languages: string[]; emergency_number?: string; late_cancel_hours?: number; late_cancel_fee?: number }
interface Ctx { me: Me | null; country: Country | null; loading: boolean; refresh: () => Promise<void>; logout: () => void; role: string; setRole: (r: string) => void }
const C = createContext<Ctx>(null as any);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [country, setCountry] = useState<Country | null>(null);
  const [loading, setLoading] = useState(!!getToken());
  const [role, setRole] = useState("");
  const refresh = useCallback(async () => {
    if (!getToken()) { setMe(null); setLoading(false); return; }
    try {
      const m = await api<Me>("/profiles/me");
      setMe(m);
      setCountry(await api<Country>(`/meta/country/${m.country}`));
    } catch (e: any) { if (e.status === 401) { setToken(""); setMe(null); } }
    setLoading(false);
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const logout = async () => { try {await disablePush();} catch { /* permission may already be revoked */ } setRole(""); setToken(""); setMe(null); };
  return <C.Provider value={{ me, country, loading, refresh, logout, role, setRole }}>{children}</C.Provider>;
}
export const useSession = () => useContext(C);
