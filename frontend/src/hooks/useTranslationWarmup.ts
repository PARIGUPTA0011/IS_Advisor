import { useEffect, useRef, useState } from "react";
import { getHealth } from "../api/health";
import type { WarmupStatus } from "../types/api";

const FAST_POLL_MS = 3000; // while loading, so the "preparing" banner clears promptly
const SLOW_POLL_MS = 60000; // once ready/failed, just enough to notice a restart

/**
 * Tracks GET /health's `warmup` field: whether the translation model has
 * finished loading in the background.
 *
 * This exists because of a real bug: the model used to load lazily, inside
 * the first non-English request's own response time (~20s measured on a
 * typical machine, longer under memory pressure) - which either raced the
 * frontend's timeout or, if the dev server had just restarted, made "every"
 * non-English query look broken. Warm-up now happens once at server startup
 * (see api/main.py's lifespan and multilingual/translate.py::warm_up), and
 * this hook is what lets the UI say "still preparing" honestly instead of
 * letting a query silently race a cold model load.
 *
 * English queries never need this: multilingual.detect() resolves already-
 * English text without touching the translator at all.
 */
export function useTranslationWarmup() {
  const [warmup, setWarmup] = useState<WarmupStatus | null>(null);
  const [reachable, setReachable] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const health = await getHealth();
        if (cancelled) return;
        setReachable(true);
        setWarmup(health.warmup ?? null);
        const stillLoading = !health.warmup || health.warmup.state === "loading" || health.warmup.state === "not_started";
        timerRef.current = setTimeout(poll, stillLoading ? FAST_POLL_MS : SLOW_POLL_MS);
      } catch {
        if (cancelled) return;
        setReachable(false);
        // The backend may just be starting up - keep checking at the fast
        // interval rather than giving up.
        timerRef.current = setTimeout(poll, FAST_POLL_MS);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const isPreparing = reachable && (warmup?.state === "loading" || warmup?.state === "not_started");

  return { warmup, reachable, isPreparing };
}
