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
    <div className="relative min-h-full overflow-hidden">
      <div className="chakra-motif" />
      <div className="relative mx-auto max-w-6xl px-4 py-10 md:px-8 md:py-16">
        <div className="pointer-events-none absolute right-0 top-4 hidden w-80 opacity-50 lg:block" aria-hidden="true">
          <svg viewBox="0 0 360 260" className="h-auto w-full text-accent-primary">
            <g fill="none" stroke="currentColor" strokeWidth="1"><path d="M28 188 92 126 160 164 218 72 302 112" /><path d="M92 126 116 42 218 72 248 210 302 112" /><path d="M28 188 78 224 248 210" /></g>
            <g fill="currentColor"><circle cx="28" cy="188" r="4" /><circle cx="78" cy="224" r="3" /><circle cx="92" cy="126" r="5" /><circle cx="116" cy="42" r="4" /><circle cx="160" cy="164" r="3" /><circle cx="218" cy="72" r="5" /><circle cx="248" cy="210" r="4" /><circle cx="302" cy="112" r="5" /></g>
          </svg>
        </div>

        <div className="relative mx-auto max-w-4xl text-center">
          <div className="mb-5 inline-flex rounded-full border border-accent-primary/25 bg-accent-primary/8 px-3 py-1.5 font-mono text-[10px] font-semibold tracking-[0.18em] text-accent-primary">
            HYBRID SEARCH · KNOWLEDGE GRAPH · GROUNDED LLM
          </div>
          <motion.h1 initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="font-display text-4xl font-bold tracking-tight text-text-primary md:text-6xl">
            {t("dashboard.heading")}
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }} className="mx-auto mt-5 max-w-2xl text-sm leading-7 text-text-secondary md:text-base">
            {t("dashboard.subheading")}
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.2 }} className="mt-9">
            <AnimatePresence mode="wait">
              {isLoading ? <motion.div key="progress" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><AnalysisProgress hasFile={false} /></motion.div> : (
                <motion.div key="input" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                  <div className="glass-panel mx-auto flex max-w-3xl items-end gap-2 rounded-3xl p-2.5 pl-5 text-left">
                    <Search size={18} className="mb-3 shrink-0 text-text-muted" />
                    <textarea value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("dashboard.placeholder")} rows={3} className="min-h-20 min-w-0 flex-1 resize-none bg-transparent py-2 text-sm leading-6 text-text-primary placeholder:text-text-muted focus:outline-none" />
                    <div className="flex shrink-0 flex-col items-center gap-2 pb-0.5 sm:flex-row">
                      <button type="button" onClick={() => navigate("/analyze")} aria-label={t("analyze.modeUpload")} className="flex size-10 items-center justify-center rounded-2xl border border-border-strong text-text-secondary transition-colors hover:border-accent-primary hover:text-accent-primary"><Upload size={17} /></button>
                      <button type="button" onClick={handleAnalyze} disabled={!query.trim()} className="flex shrink-0 items-center gap-1.5 rounded-2xl bg-brand-gradient px-5 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-muted disabled:opacity-100">{t("dashboard.analyze")}<ArrowRight size={15} /></button>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-text-muted"><span>{t("dashboard.tryExample")}:</span>{EXAMPLE_KEYS.map((key) => <button key={key} type="button" onClick={() => setQuery(t(key))} className="rounded-full border border-border px-3 py-1 text-accent-primary transition-colors hover:bg-accent-primary/10">{t(key)}</button>)}</div>
                  <div className="mx-auto mt-8 grid max-w-3xl gap-3 text-left sm:grid-cols-3">{([[FileText, "1", t("dashboard.steps.oneTitle"), t("dashboard.steps.oneBody")], [BrainCircuit, "2", t("dashboard.steps.twoTitle"), t("dashboard.steps.twoBody")], [ArrowRight, "3", t("dashboard.steps.threeTitle"), t("dashboard.steps.threeBody")]] as Array<[typeof FileText, string, string, string]>).map(([Icon, step, title, body]) => <div key={step} className="rounded-2xl border border-border bg-bg-elevated/60 p-4"><div className="mb-3 flex items-center gap-2 text-xs font-semibold text-accent-primary"><Icon size={15} /> STEP {step}</div><p className="text-sm font-semibold text-text-primary">{title}</p><p className="mt-1 text-xs leading-5 text-text-muted">{body}</p></div>)}</div>
                  <div className="mx-auto mt-8 grid max-w-3xl gap-3 sm:grid-cols-2"><div className="rounded-2xl border border-border bg-bg-elevated/60 px-5 py-4 text-left"><strong className="block text-2xl tracking-tight text-text-primary">35,524</strong><span className="text-xs text-text-muted">{t("dashboard.standardsIndexed", { defaultValue: "Standards indexed" })}</span></div><div className="rounded-2xl border border-border bg-bg-elevated/60 px-5 py-4 text-left"><strong className="block text-2xl tracking-tight text-text-primary">22</strong><span className="text-xs text-text-muted">{t("dashboard.targetLanguages", { defaultValue: "Target languages" })}</span></div></div>
                  <Link to="/analyze" className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-text-muted transition-colors hover:text-accent-primary"><Upload size={13} />{t("analyze.modeUpload")}<ArrowRight size={12} /></Link>
                </motion.div>
              )}
            </AnimatePresence>
            {status === "error" && error && <div className="mt-5"><ErrorState message={error} onRetry={reset} /></div>}
          </motion.div>
        </div>
      </div>
    </div>
  );
}

// keep the landing page focused on the search workflow while preserving the existing API flow
// The visual treatment below is shared by both theme modes.
