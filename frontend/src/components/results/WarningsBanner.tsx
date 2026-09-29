import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

interface Props {
  warnings: string[];
  /** Same order/length as `warnings` - present only for a non-English query
   * (see rag/pipeline.py::localise_response). Shown beside the English
   * warning, never instead of it. */
  warningsLocalized?: string[];
  rtl?: boolean;
}

export function WarningsBanner({ warnings, warningsLocalized, rtl }: Props) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;

  return (
    <div className="rounded-2xl border border-status-warning/25 bg-status-warning/5 p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-status-warning">
        <AlertTriangle size={13} />
        {t("results.warnings")}
      </p>
      <ul className="space-y-2">
        {warnings.map((w, i) => {
          const localized = warningsLocalized?.[i];
          const showLocalized = localized && localized !== w;
          return (
            <li key={i} className="text-sm text-text-secondary">
              <p>{w}</p>
              {showLocalized && (
                <p className="mt-0.5 text-text-primary" dir={rtl ? "rtl" : undefined}>
                  {localized}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
