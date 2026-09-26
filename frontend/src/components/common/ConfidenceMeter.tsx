import { useTranslation } from "react-i18next";
import type { Confidence } from "../../types/api";

const CONFIDENCE_META: Record<Confidence, { fraction: number; color: string; label: string }> = {
  high: { fraction: 1, color: "var(--color-emerald-500)", label: "High" },
  medium: { fraction: 0.65, color: "var(--accent-gold)", label: "Medium" },
  low: { fraction: 0.35, color: "var(--color-amber-500)", label: "Low" },
  insufficient_evidence: { fraction: 0.08, color: "var(--color-rose-500)", label: "Insufficient evidence" },
  parse_error: { fraction: 0, color: "var(--color-rose-500)", label: "Parse error" },
  unknown: { fraction: 0.2, color: "var(--text-muted)", label: "Unknown" },
};

export function ConfidenceMeter({ confidence }: { confidence: Confidence }) {
  const { t } = useTranslation();
  const meta = CONFIDENCE_META[confidence] ?? CONFIDENCE_META.unknown;

  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-28 overflow-hidden rounded-full bg-surface-muted">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${meta.fraction * 100}%`, background: meta.color }}
        />
      </div>
      <span className="text-sm font-medium" style={{ color: meta.color }}>
        {t(`confidence.${confidence}`, meta.label)}
      </span>
    </div>
  );
}
