import { useEffect, useState } from "react";
import { Clock3, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { RecommendResponse } from "../types/api";

const HISTORY_KEY = "is-advisor-history";

type HistoryEntry = { query: string; timestamp: string; response: RecommendResponse };

function readHistory(): HistoryEntry[] {
  try {
    const stored = window.localStorage.getItem(HISTORY_KEY);
    if (!stored) return [];
    const parsed = JSON.parse(stored) as HistoryEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function relativeTime(timestamp: string, t: (key: string, options?: Record<string, unknown>) => string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000));
  if (seconds < 60) return t("history.justNow");
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t("history.minutesAgo", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("history.hoursAgo", { count: hours });
  return t("history.daysAgo", { count: Math.floor(hours / 24) });
}

export function EntryPoint() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [entries, setEntries] = useState<HistoryEntry[]>([]);

  useEffect(() => {
    setEntries(readHistory());
  }, []);

  const clearHistory = () => {
    window.localStorage.removeItem(HISTORY_KEY);
    setEntries([]);
  };

  return (
    <section className="mx-auto max-w-5xl px-4 py-12 md:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex size-12 items-center justify-center rounded-2xl bg-accent-primary/10 text-accent-primary"><Clock3 size={24} /></div>
          <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-accent-primary">{t("history.recentAnalyses")}</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-text-primary">{t("history.yourHistory")}</h1>

        </div>
        {entries.length > 0 && <button type="button" onClick={clearHistory} className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm font-medium text-text-secondary hover:bg-surface-muted hover:text-text-primary"><Trash2 size={15} />{t("history.clear")}</button>}
      </div>
      {entries.length === 0 ? (
        <div className="mt-8 rounded-3xl border border-dashed border-border bg-bg-elevated p-10 text-center">
          <Clock3 className="mx-auto text-text-muted" size={28} />
          <h2 className="mt-4 text-lg font-semibold text-text-primary">{t("history.emptyTitle")}</h2>
          <p className="mt-2 text-sm text-text-secondary">{t("history.emptyBody")}</p>
          <button type="button" onClick={() => navigate("/analyze")} className="mt-5 rounded-xl bg-accent-primary px-4 py-2.5 text-sm font-semibold text-text-on-primary">{t("history.analyze")}</button>
        </div>
      ) : (
        <div className="mt-8 grid gap-3">
          {entries.map((entry, index) => (
            <button key={`${entry.timestamp}-${index}`} type="button" onClick={() => navigate("/results", { state: { result: entry.response } })} className="rounded-2xl border border-border bg-bg-elevated p-5 text-start transition-colors hover:border-accent-primary/50 hover:bg-surface-muted">
              <p className="line-clamp-2 text-sm font-medium text-text-primary">{entry.query}</p>
              <p className="mt-2 text-xs text-text-muted">{relativeTime(entry.timestamp, t)}</p>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
