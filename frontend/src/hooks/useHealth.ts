import { useCallback, useEffect, useState } from "react";
import { getHealth } from "../api/health";
import type { HealthResponse } from "../types/api";

type Status = "loading" | "online" | "offline";

export function useHealth(pollMs = 30000) {
  const [status, setStatus] = useState<Status>("loading");
  const [data, setData] = useState<HealthResponse | null>(null);

  const checkHealth = useCallback(async () => {
    try {
      const result = await getHealth();
      setData(result);
      setStatus("online");
    } catch {
      setData(null);
      setStatus("offline");
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    const interval = setInterval(() => void checkHealth(), pollMs);
    return () => clearInterval(interval);
  }, [checkHealth, pollMs]);

  return { status, data, retry: checkHealth };
}
