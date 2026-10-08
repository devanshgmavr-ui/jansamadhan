import { useEffect, useRef } from "react";

// Conservative server refresh (G6). Polls at a slow interval while the tab
// is visible; pauses when hidden; single interval per hook instance with
// full cleanup on unmount. Refresh failures must be handled by the
// callback itself (never crash here). The backend remains authoritative:
// this only re-reads server state, on a 30–60s cadence by default.
export function usePolling(callback, intervalMs = 45000) {
  const saved = useRef(null);

  useEffect(() => {
    saved.current = callback;
  });

  useEffect(() => {
    if (intervalMs <= 0) return undefined;
    let id = null;
    const start = () => {
      if (id !== null) return;
      id = setInterval(() => {
        saved.current();
      }, intervalMs);
    };
    const stop = () => {
      if (id !== null) {
        clearInterval(id);
        id = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) {
        stop();
      } else {
        saved.current();
        start();
      }
    };
    start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, [intervalMs]);
}
