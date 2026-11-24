import { useCallback, useEffect, useRef, useState } from "react";
import type { Point } from "./WorkMap";

export function useWorkLocation() {
  const [point, setPoint] = useState<Point>();
  const [status, setStatus] = useState<"locating" | "device" | "manual" | "denied">("locating");
  const generation = useRef(0);

  const choose = useCallback((next: Point) => {
    generation.current++;
    setPoint(next);
    setStatus("manual");
  }, []);

  const locate = useCallback(() => {
    const request = ++generation.current;
    setStatus("locating");
    const fail = () => { if (generation.current === request) setStatus("denied"); };
    if (!navigator.geolocation) { fail(); return; }
    navigator.geolocation.getCurrentPosition(({ coords }) => {
      if (generation.current !== request) return;
      setPoint({ lat: coords.latitude, lon: coords.longitude });
      setStatus("device");
    }, fail, { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 });
  }, []);

  useEffect(() => { locate(); return () => { generation.current++; }; }, [locate]);
  return { point, status, choose, locate };
}
export type WorkLocation = ReturnType<typeof useWorkLocation>;
