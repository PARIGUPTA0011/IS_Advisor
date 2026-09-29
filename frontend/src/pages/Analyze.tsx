import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, Type, X } from "lucide-react";
import { UploadDropzone } from "../components/analyze/UploadDropzone";
import { AnalysisProgress } from "../components/analyze/AnalysisProgress";
import { MicButton } from "../components/analyze/MicButton";
import { ErrorState } from "../components/common/ErrorState";
import { WarmupBanner } from "../components/common/WarmupBanner";
import { useRecommend } from "../hooks/useRecommend";
import { useSpeechToText } from "../hooks/useSpeechToText";
import { useAnalysisPrefs } from "../contexts/AnalysisPrefsContext";
import { useTranslationWarmup } from "../hooks/useTranslationWarmup";
// apiLanguageName is deliberately NOT used to set the request's `language`
// field any more - see the comment on handleSubmit below.

const EXAMPLE_KEYS = [
  "analyze.examples.led",
  "analyze.examples.pumps",
  "analyze.examples.cables",
] as const;

type Mode = "text" | "upload";

export function Analyze() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { topK } = useAnalysisPrefs();
  const { isPreparing } = useTranslationWarmup();
  const { status, error, runQuery, runDocument, reset } = useRecommend();

  const [mode, setMode] = useState<Mode>("text");
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const isLoading = status === "loading";

  const handleSubmit = async () => {
    // `language` is intentionally omitted here. It used to be set to
    // apiLanguageName(i18n.language) - the UI's own display language - and
    // sent on every request. The backend treats an explicit `language` as
    // authoritative over whatever the text actually is (the same way
    // `run_query.py --lang` overrides detection), so a query typed or
    // dictated in Hindi while the UI happened to be showing English was
    // being forced through the pipeline AS English: never translated, and
    // searched against an English-only index. Leaving it out lets the
    // backend detect the language from the query itself, exactly like
    // run_query.py does by default, and the detected language comes back on
    // the response as `language` and is shown on the results page.
    const result =
      mode === "text"
        ? await runQuery(query.trim(), { top_k: topK })
        : file
          ? await runDocument(file, { top_k: topK })
          : null;
    if (result) navigate("/results", { state: { result } });
  };

  const canSubmit = mode === "text"
    ? query.trim().length > 0 && !(isPreparing && /[^\u0000-\u024f\u1e00-\u1eff]/u.test(query))
    : file !== null;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 md:px-8">
      <h1 className="font-display text-3xl font-semibold text-text-primary">{t("nav.analyze")}</h1>
      <p className="mt-2 text-sm text-text-secondary">{t("dashboard.subheading")}</p>

      <WarmupBanner />

      <div className="mt-6 flex gap-2">
        {(["text", "upload"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              mode === m
                ? "bg-accent-primary text-text-on-primary"
                : "bg-surface-muted text-text-secondary hover:text-text-primary"
            }`}
          >
            {m === "text" ? <Type size={15} /> : <FileText size={15} />}
            {m === "text" ? t("analyze.modeText") : t("analyze.modeUpload")}
          </button>
        ))}
      </div>

      <div className="mt-5">
        <AnimatePresence mode="wait">
          {isLoading ? (
            <motion.div
              key="progress"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="py-6"
            >
              <AnalysisProgress hasFile={mode === "upload"} />
            </motion.div>
          ) : mode === "text" ? (
            <motion.div
              key="text"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <TextPanel
                query={query}
                setQuery={setQuery}
                t={t}
                disabled={isLoading}
              />

              <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-text-muted">
                <span>{t("dashboard.tryExample")}:</span>
                {EXAMPLE_KEYS.map((key) => {
                  const example = t(key);
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setQuery(example)}
                      className="rounded-full border border-border px-3 py-1 text-accent-primary transition-colors hover:bg-accent-primary/10"
                    >
                      {example.slice(0, 28)}…
                    </button>
                  );
                })}
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="upload"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <UploadDropzone
                file={file}
                onFileSelected={setFile}
                onClear={() => setFile(null)}
                error={null}
              />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {status === "error" && error && (
        <div className="mt-5">
          <ErrorState message={error} onRetry={reset} />
        </div>
      )}

      {!isLoading && (
        <button
          type="button"
          disabled={!canSubmit}
          onClick={handleSubmit}
          className="mt-6 w-full rounded-2xl bg-accent-primary py-3.5 text-sm font-semibold text-text-on-primary transition-colors hover:bg-[var(--accent-primary-hover)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t("analyze.analyzeButton")}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-component: textarea panel with mic button wired in
// ---------------------------------------------------------------------------

interface TextPanelProps {
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  t: (key: string, opts?: Record<string, unknown>) => string;
  disabled: boolean;
}

function TextPanel({ query, setQuery, t, disabled }: TextPanelProps) {
  const speech = useSpeechToText({
    onTranscript: (text) => {
      // Append to existing text so users can record in multiple takes and
      // accumulate a longer specification without losing what they already typed.
      setQuery((prev) => (prev.trim() ? `${prev.trim()} ${text}` : text));
    },
  });

  const showTranscriptPill = speech.status === "done" && speech.transcript !== null;
  const showSpeechError = speech.status === "error" && speech.error !== null;

  return (
    <div>
      <div className="glass-panel rounded-2xl p-4">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("dashboard.placeholder")}
          rows={6}
          disabled={disabled}
          // "auto" lets the browser's own bidi algorithm pick left-to-right or
          // right-to-left from whatever script is actually typed or pasted in
          // (Hindi, Urdu, Tamil, ...) - there is no language selector to read
          // this from in advance, and there should not be one.
          dir="auto"
          className="w-full resize-none bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none disabled:opacity-50"
        />
        <div className="flex items-center justify-between border-t border-border pt-3">
          {/* Left side: char count + mic button + status label */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">
              {t("analyze.charCount", { count: query.length })}
            </span>

            <MicButton
              status={speech.status}
              onToggle={speech.toggle}
              title={
                speech.status === "recording"
                  ? t("analyze.mic.stopRecording")
                  : t("analyze.mic.startRecording")
              }
            />

            <AnimatePresence>
              {speech.status === "recording" && (
                <motion.span
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -4 }}
                  className="text-xs font-medium text-red-500"
                >
                  {t("analyze.mic.recording")}
                </motion.span>
              )}
              {speech.status === "transcribing" && (
                <motion.span
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -4 }}
                  className="text-xs text-text-muted"
                >
                  {t("analyze.mic.transcribing")}
                </motion.span>
              )}
            </AnimatePresence>
          </div>

          {/* Right side: clear button */}
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                speech.reset();
              }}
              className="flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text-primary"
            >
              <X size={12} />
              {t("analyze.clear")}
            </button>
          )}
        </div>
      </div>

      {/* Transcript pill – shows what Whisper heard, with detected language */}
      <AnimatePresence>
        {showTranscriptPill && speech.transcript && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="mt-2 flex items-start justify-between gap-3 rounded-xl border border-border bg-surface-muted px-4 py-2.5 text-xs"
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
              <span className="text-text-primary" dir="auto">{speech.transcript.text}</span>
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
            className="mt-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-600 dark:border-red-800 dark:bg-red-950/40 dark:text-red-400"
          >
            {speech.error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
