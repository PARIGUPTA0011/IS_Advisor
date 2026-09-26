import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, BrainCircuit, FileText, Search, Upload } from "lucide-react";
import { AnalysisProgress } from "../components/analyze/AnalysisProgress";
import { ErrorState } from "../components/common/ErrorState";
import { useRecommend } from "../hooks/useRecommend";
import { useAnalysisPrefs } from "../contexts/AnalysisPrefsContext";
import { apiLanguageName } from "../i18n";

const EXAMPLE_KEYS = ["dashboard.examples.led", "dashboard.examples.pump"] as const;

export function Dashboard() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { topK } = useAnalysisPrefs();
  const { status, error, runQuery, reset } = useRecommend();
  const [query, setQuery] = useState("");

  const isLoading = status === "loading";

  const handleAnalyze = async () => {
    if (!query.trim()) return;
    const result = await runQuery(query.trim(), { top_k: topK, language: apiLanguageName(i18n.language) });
    if (result) navigate("/results", { state: { result } });
  };

  return (
    <div className="relative overflow-hidden">
      <div className="chakra-motif" />
      <div className="relative mx-auto max-w-3xl px-4 py-16 text-center md:px-8">
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="font-display text-4xl font-semibold tracking-tight text-text-primary md:text-5xl"
        >
          {t("dashboard.heading")}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="mx-auto mt-3 max-w-xl text-sm text-text-secondary md:text-base"
        >
          {t("dashboard.subheading")}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="mt-8"
        >
          <AnimatePresence mode="wait">
            {isLoading ? (
              <motion.div key="progress" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <AnalysisProgress hasFile={false} />
              </motion.div>
            ) : (
              <motion.div key="input" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <div className="glass-panel flex items-center gap-2 rounded-2xl p-2 pl-4 text-left">
                  <Search size={18} className="mt-1 shrink-0 text-text-muted" />
                  <textarea
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={t("dashboard.placeholder")}
                    rows={3}
                    className="min-h-20 min-w-0 flex-1 resize-none bg-transparent py-1.5 text-sm leading-6 text-text-primary placeholder:text-text-muted focus:outline-none"
                  />
                  <div className="flex shrink-0 flex-col items-center gap-2 self-end pb-0.5 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => navigate("/analyze")}
                      aria-label={t("analyze.modeUpload")}
                      className="flex size-10 items-center justify-center rounded-xl border border-border-strong text-text-secondary transition-colors hover:border-accent-primary hover:text-accent-primary"
                    >
                      <Upload size={17} />
                    </button>
                    <button
                      type="button"
                      onClick={handleAnalyze}
                      disabled={!query.trim()}
                      className="flex shrink-0 items-center gap-1.5 rounded-xl bg-accent-primary px-4 py-2.5 text-sm font-semibold text-text-on-primary transition-colors hover:bg-[var(--accent-primary-hover)] disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-muted"
                    >
                      {t("dashboard.analyze")}
                      <ArrowRight size={15} />
                    </button>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-text-muted">
                  <span>{t("dashboard.tryExample")}:</span>
                  {EXAMPLE_KEYS.map((key) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setQuery(t(key))}
                      className="rounded-full border border-border px-3 py-1 text-accent-primary transition-colors hover:bg-accent-primary/10"
                    >
                      {t(key)}
                    </button>
                  ))}
                </div>

                <div className="mt-8 grid gap-3 text-left sm:grid-cols-3">
                  {( [
                    [FileText, "1", "Define your spec", "Describe requirements or upload a tender."],
                    [BrainCircuit, "2", "Retrieve knowledge", "Search the standards corpus and graph."],
                    [ArrowRight, "3", "Get recommendations", "Review evidence-backed standards."],
                  ] as Array<[typeof FileText, string, string, string]>).map(([Icon, step, title, body]) => {
                    const StepIcon = Icon as typeof FileText;
                    return (
                      <div key={step as string} className="rounded-2xl border border-border bg-bg-elevated/60 p-4">
                        <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-accent-primary">
                          <StepIcon size={15} /> STEP {step}
                        </div>
                        <p className="text-sm font-semibold text-text-primary">{title}</p>
                        <p className="mt-1 text-xs leading-5 text-text-muted">{body}</p>
                      </div>
                    );
                  })}
                </div>

                <Link
                  to="/analyze"
                  className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-text-muted transition-colors hover:text-accent-primary"
                >
                  <Upload size={13} />
                  {t("analyze.modeUpload")}
                  <ArrowRight size={12} />
                </Link>
              </motion.div>
            )}
          </AnimatePresence>

          {status === "error" && error && (
            <div className="mt-5">
              <ErrorState message={error} onRetry={reset} />
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
