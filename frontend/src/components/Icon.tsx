const strokes = {
  pin: "M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
  target: "M12 2v3m0 14v3M2 12h3m14 0h3M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-5 0a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z",
  work: "M3 7h18v14H3zM8 7V4h8v3M3 12c5 3 13 3 18 0m-9 0v4",
  hire: "M3 21V9l9-7 9 7v12H3Zm6 0v-7h6v7",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  back: "M19 12H5m6-6-6 6 6 6",
  plus: "M12 5v14M5 12h14",
  map: "m2 5 6-2 8 3 6-2v15l-6 2-8-3-6 2V5Zm6-2v15m8-12v15",
  user: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21c0-9 16-9 16 0",
  clock: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-5v6l4 2",
  check: "m4 12 5 5L20 6",
  search: "M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-2 5 6 6",
};
export function Icon({ name, size = 20 }: { name: keyof typeof strokes; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={strokes[name]} /></svg>;
}
