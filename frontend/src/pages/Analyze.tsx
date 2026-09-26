import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { FileText, Type, X } from "lucide-react";
import { UploadDropzone } from "../components/analyze/UploadDropzone";
import { AnalysisProgress } from "../components/analyze/AnalysisProgress";
import { ErrorState } from "../components/common/ErrorState";
import { useRecommend } from "../hooks/useRecommend";
import { useAnalysisPrefs } from "../contexts/AnalysisPrefsContext";
import { apiLanguageName } from "../i18n";

const EXAMPLE_KEYS = [
  "analyze.examples.led",
  "analyze.examples.pumps",
  "analyze.examples.cables",
] as const;

type Mode = "text" | "upload";

export function Analyze() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { topK } = useAnalysisPrefs();
  const { status, error, runQuery, runDocument, reset } = useRecommend();

  const [mode, setMode] = useState<Mode>("text");
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);

  const isLoading = status === "loading";
  const language = apiLanguageName(i18n.language);

  const handleSubmit = async () => {
    const result =
      mode === "text"
        ? await runQuery(query.trim(), { top_k: topK, language })
        : file
          ? await runDocument(file, { top_k: topK, language })
          : null;
    if (result) navigate("/results", { state: { result } });
  };

  const canSubmit = mode === "text" ? query.trim().length > 0 : file !== null;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 md:px-8">
      <h1 className="font-display text-3xl font-semibold text-text-primary">{t("nav.analyze")}</h1>
      <p className="mt-2 text-sm text-text-secondary">{t("dashboard.subheading")}</p>

      <div className="mt-6 flex gap-2">
        {(["text", "upload"] as Mode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={`flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-colors ${
              mode === m ? "bg-accent-primary text-text-on-primary" : "bg-surface-muted text-text-secondary hover:text-text-primary"
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
            <motion.div key="progress" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="py-6">
              <AnalysisProgress hasFile={mode === "upload"} />
            </motion.div>
          ) : mode === "text" ? (
            <motion.div key="text" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <div className="glass-panel rounded-2xl p-4">
                <textarea
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={t("dashboard.placeholder")}
                  rows={6}
                  className="w-full resize-none bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
                />
                <div className="flex items-center justify-between border-t border-border pt-3">
                  <span className="text-xs text-text-muted">{t("analyze.charCount", { count: query.length })}</span>
                  {query && (
                    <button
                      type="button"
                      onClick={() => setQuery("")}
                      className="flex items-center gap-1 text-xs font-medium text-text-muted hover:text-text-primary"
                    >
                      <X size={12} />
                      {t("analyze.clear")}
                    </button>
                  )}
                </div>
              </div>

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
            <motion.div key="upload" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <UploadDropzone file={file} onFileSelected={setFile} onClear={() => setFile(null)} error={null} />
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
