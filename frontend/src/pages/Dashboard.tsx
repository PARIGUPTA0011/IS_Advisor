import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, BrainCircuit, FileText, Search, Upload, X } from "lucide-react";
import { AnalysisProgress } from "../components/analyze/AnalysisProgress";
import { MicButton } from "../components/analyze/MicButton";
import { ErrorState } from "../components/common/ErrorState";
import { WarmupBanner } from "../components/common/WarmupBanner";
import { useRecommend } from "../hooks/useRecommend";
import { useSpeechToText } from "../hooks/useSpeechToText";
import { useAnalysisPrefs } from "../contexts/AnalysisPrefsContext";
import { useTranslationWarmup } from "../hooks/useTranslationWarmup";
// apiLanguageName is deliberately NOT used to set the request's `language`
// any more - see the comment on handleAnalyze below.

const EXAMPLE_KEYS = ["dashboard.examples.led", "dashboard.examples.pump"] as const;

export function Dashboard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { topK } = useAnalysisPrefs();
  const { isPreparing } = useTranslationWarmup();
  const { status, error, runQuery, reset } = useRecommend();
  const [query, setQuery] = useState("");

  const isLoading = status === "loading";

  const speech = useSpeechToText({
    onTranscript: (text) => {
      setQuery((prev) => (prev.trim() ? `${prev.trim()} ${text}` : text));
    },
  });

  const handleAnalyze = async () => {
    if (!query.trim()) return;
    // `language` is intentionally omitted - see the identical fix and full
    // explanation in Analyze.tsx's handleSubmit. This quick-search box on the
    // homepage was a second, independent place forcing the interface's
    // display language onto every query, which is what caused a Tamil/Hindi/
    // Urdu query typed or dictated here to come back detected as English.
    const result = await runQuery(query.trim(), { top_k: topK });
    if (result) navigate("/results", { state: { result } });
  };

  const showTranscriptPill = speech.status === "done" && speech.transcript !== null;
  const showSpeechError = speech.status === "error" && speech.error !== null;

  return (
    <div className="relative overflow-hidden">
      <div className="chakra-motif" />
      <svg
        aria-hidden="true"
        viewBox="0 0 360 260"
        className="pointer-events-none absolute -right-20 top-6 hidden h-64 w-90 opacity-[0.16] text-accent-primary sm:block"
      >
        <g fill="none" stroke="currentColor" strokeWidth="1">
          <path d="M28 188 92 126 160 164 218 72 302 112" />
          <path d="M92 126 116 42 218 72 248 210 302 112" />
          <path d="M28 188 78 224 248 210" />
        </g>
        <g fill="currentColor">
          <circle cx="28" cy="188" r="4" />
          <circle cx="78" cy="224" r="3" />
          <circle cx="92" cy="126" r="5" />
          <circle cx="116" cy="42" r="4" />
          <circle cx="160" cy="164" r="3" />
          <circle cx="218" cy="72" r="5" />
          <circle cx="248" cy="210" r="4" />
          <circle cx="302" cy="112" r="5" />
        </g>
      </svg>
      <div className="relative mx-auto max-w-3xl px-4 py-16 text-center md:px-8">
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="break-words font-display text-4xl font-semibold tracking-tight text-text-primary md:text-5xl"
        >
          {t("dashboard.heading")}
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
          className="mx-auto mt-3 max-w-xl break-words text-sm text-text-secondary md:text-base"
        >
          {t("dashboard.subheading")}
        </motion.p>

        <div className="mx-auto mt-4 max-w-xl text-start">
          <WarmupBanner />
        </div>

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
                <div className="glass-panel flex items-center gap-2 rounded-2xl p-2 ps-4 text-start">
                  <Search size={18} className="mt-1 shrink-0 text-text-muted" />
                  <textarea
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={t("dashboard.placeholder")}
                    rows={3}
                    className="min-h-20 min-w-0 flex-1 resize-none bg-transparent py-1.5 text-sm leading-6 text-text-primary placeholder:text-text-muted focus:outline-none"
                  />
                  <div className="flex shrink-0 flex-col items-center gap-2 self-end pb-0.5 sm:flex-row">
                    {/* Upload button */}
                    <button
                      type="button"
                      onClick={() => navigate("/analyze")}
                      aria-label={t("analyze.modeUpload")}
                      className="flex size-10 items-center justify-center rounded-xl border border-border-strong text-text-secondary transition-colors hover:border-accent-primary hover:text-accent-primary"
                    >
                      <Upload size={17} />
                    </button>

                    {/* Mic button */}
                    <MicButton
                      status={speech.status}
                      onToggle={speech.toggle}
                      title={
                        speech.status === "recording"
                          ? t("analyze.mic.stopRecording")
                          : t("analyze.mic.startRecording")
                      }
                    />

                    {/* Analyze button */}
                    <button
                      type="button"
                      onClick={handleAnalyze}
                      disabled={!query.trim() || (isPreparing && /[^\u0000-\u024f\u1e00-\u1eff]/u.test(query))}
                      className="flex shrink-0 items-center gap-1.5 rounded-xl bg-accent-primary px-4 py-2.5 text-sm font-semibold text-text-on-primary transition-colors hover:bg-[var(--accent-primary-hover)] disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-text-muted"
                    >
                      {t("dashboard.analyze")}
                      <ArrowRight size={15} />
                    </button>
                  </div>
                </div>

                {/* Recording / transcribing status */}
                <AnimatePresence>
                  {speech.status === "recording" && (
                    <motion.p
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      className="mt-2 text-xs font-medium text-red-500"
                    >
                      {t("analyze.mic.recording")}
                    </motion.p>
                  )}
                  {speech.status === "transcribing" && (
                    <motion.p
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -4 }}
                      className="mt-2 text-xs text-text-muted"
                    >
                      {t("analyze.mic.transcribing")}
                    </motion.p>
                  )}
                </AnimatePresence>

                {/* Transcript pill */}
                <AnimatePresence>
                  {showTranscriptPill && speech.transcript && (
                    <motion.div
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                      className="mt-2 flex items-start justify-between gap-3 rounded-xl border border-border bg-surface-muted px-4 py-2.5 text-start text-xs"
                    >
                      <div className="min-w-0">
                        <span className="font-medium text-text-secondary">
                          {t("analyze.mic.heard")}
                          {speech.transcript.language_name &&
                          speech.transcript.language_name.toLowerCase() !== "english" ? (
                            <span className="ms-1 text-text-muted">
                              ({speech.transcript.language_name})
                            </span>
                          ) : null}
                          {": "}
                        </span>
                        <span className="text-text-primary">{speech.transcript.text}</span>
                      </div>
                      <button
                        type="button"
                        onClick={speech.reset}
                        aria-label={t("analyze.mic.dismissTranscript")}
                        className="shrink-0 text-text-muted hover:text-text-primary"
                      >
                        <X size={13} />
                      </button>
                    </motion.div>
                  )}

                  {showSpeechError && (
                    <motion.p
                      initial={{ opacity: 0, y: -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -6 }}
                      className="mt-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-start text-xs text-red-600 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400"
                    >
                      {speech.error}
                    </motion.p>
                  )}
                </AnimatePresence>

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

                <div className="mt-8 grid gap-3 text-start sm:grid-cols-3">
                  {( [
                    [FileText, "1", t("dashboard.steps.oneTitle"), t("dashboard.steps.oneBody")],
                    [BrainCircuit, "2", t("dashboard.steps.twoTitle"), t("dashboard.steps.twoBody")],
                    [ArrowRight, "3", t("dashboard.steps.threeTitle"), t("dashboard.steps.threeBody")],
                  ] as Array<[typeof FileText, string, string, string]>).map(([Icon, step, title, body]) => {
                    const StepIcon = Icon as typeof FileText;
                    return (
                      <div key={step as string} className="rounded-2xl border border-border bg-bg-elevated/60 p-4">
                        <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-accent-primary">
                          <StepIcon size={15} /> {t("dashboard.stepLabel", { step })}
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
