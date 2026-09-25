import { useEffect, useState } from "react";

/** Wall-clock milliseconds, re-rendering on an interval aligned to the second. */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    let timer = 0;
    const tick = () => {
      setNow(Date.now());
      timer = window.setTimeout(tick, intervalMs - (Date.now() % intervalMs));
    };
    timer = window.setTimeout(tick, intervalMs - (Date.now() % intervalMs));
    return () => window.clearTimeout(timer);
  }, [intervalMs]);
  return now;
}
