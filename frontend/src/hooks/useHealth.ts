import { useEffect, useState } from "react";
import { getHealth } from "../api/health";
import type { HealthResponse } from "../types/api";

type Status = "loading" | "online" | "offline";

export function useHealth(pollMs = 30000) {
  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const result = await getHealth();
        if (!cancelled) {
          setData(result);
          setStatus("online");
        }
      } catch {
        if (!cancelled) {
          setStatus("offline");
          setData(null);
        }
      }
    }

    check();
    const interval = setInterval(check, pollMs);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pollMs]);

  return { status, data };
}
