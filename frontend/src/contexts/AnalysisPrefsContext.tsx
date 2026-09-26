import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

interface AnalysisPrefsValue {
  topK: number;
  setTopK: (n: number) => void;
}

const STORAGE_KEY = "isadvisor.topK";
const DEFAULT_TOP_K = 10;

const AnalysisPrefsContext = createContext<AnalysisPrefsValue | null>(null);

function readStoredTopK(): number {
  try {
    const stored = Number(window.localStorage.getItem(STORAGE_KEY));
    if (Number.isFinite(stored) && stored >= 1 && stored <= 50) return stored;
  } catch {
    // best-effort only
  }
  return DEFAULT_TOP_K;
}

export function AnalysisPrefsProvider({ children }: { children: ReactNode }) {
  const [topK, setTopKState] = useState<number>(readStoredTopK);

  const setTopK = (n: number) => {
    setTopKState(n);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(n));
    } catch {
      // best-effort only
    }
  };

  const value = useMemo(() => ({ topK, setTopK }), [topK]);
  return <AnalysisPrefsContext.Provider value={value}>{children}</AnalysisPrefsContext.Provider>;
}

export function useAnalysisPrefs(): AnalysisPrefsValue {
  const ctx = useContext(AnalysisPrefsContext);
  if (!ctx) throw new Error("useAnalysisPrefs must be used within an AnalysisPrefsProvider");
  return ctx;
}
