import { useCallback, useState } from "react";
import { recommend, recommendDocument } from "../api/analysis";
import { ApiError } from "../api/client";
import type { RecommendResponse } from "../types/api";

type Status = "idle" | "loading" | "success" | "error";

interface State {
  status: Status;
  data: RecommendResponse | null;
  error: string | null;
}

export function useRecommend() {
  const [state, setState] = useState<State>({ status: "idle", data: null, error: null });

  const runQuery = useCallback(async (query: string, opts: { top_k?: number; language?: string | null } = {}) => {
    setState({ status: "loading", data: null, error: null });
    try {
      const data = await recommend({ query, top_k: opts.top_k, language: opts.language });
      setState({ status: "success", data, error: null });
      return data;
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
      setState({ status: "error", data: null, error: message });
      return null;
    }
  }, []);

  const runDocument = useCallback(
    async (file: File, opts: { top_k?: number; language?: string | null } = {}) => {
      setState({ status: "loading", data: null, error: null });
      try {
        const data = await recommendDocument(file, opts);
        setState({ status: "success", data, error: null });
        return data;
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
        setState({ status: "error", data: null, error: message });
        return null;
      }
    },
    [],
  );

  const reset = useCallback(() => setState({ status: "idle", data: null, error: null }), []);

  return { ...state, runQuery, runDocument, reset };
}
