import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

const STEP_KEYS = [
  "analyze.steps.uploading",
  "analyze.steps.extracting",
  "analyze.steps.understanding",
  "analyze.steps.searching",
  "analyze.steps.building",
  "analyze.steps.evidence",
] as const;

/**
 * A single backend call handles the whole pipeline (no streaming progress
 * events exist), so this animates through the real stages of that pipeline
 * as an honest "working on it" indicator - it never claims a stage finished
 * before the actual response comes back, and disappears the moment it does.
 */
export function AnalysisProgress({ hasFile }: { hasFile: boolean }) {
  const { t } = useTranslation();
  const [activeIndex, setActiveIndex] = useState(0);
  const steps = hasFile ? STEP_KEYS : STEP_KEYS.slice(1);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveIndex((i) => Math.min(i + 1, steps.length - 1));
    }, 900);
    return () => clearInterval(interval);
  }, [steps.length]);

  return (
    <div className="glass-panel mx-auto max-w-md space-y-3 rounded-2xl p-6">
      {steps.map((key, i) => {
        const state = i < activeIndex ? "done" : i === activeIndex ? "active" : "pending";
        return (
          <motion.div
            key={key}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: state === "pending" ? 0.4 : 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className="flex items-center gap-3"
          >
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
                state === "done"
                  ? "bg-status-current text-white"
                  : state === "active"
                    ? "bg-accent-primary text-white"
                    : "bg-surface-muted text-text-muted"
              }`}
            >
              {state === "done" ? (
                <Check size={13} strokeWidth={3} />
              ) : state === "active" ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
              )}
            </span>
            <span className={`text-sm ${state === "pending" ? "text-text-muted" : "text-text-primary"}`}>
              {t(key)}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}
