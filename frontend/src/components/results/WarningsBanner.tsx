import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";

export function WarningsBanner({ warnings }: { warnings: string[] }) {
  const { t } = useTranslation();
  if (warnings.length === 0) return null;

  return (
    <div className="rounded-2xl border border-status-warning/25 bg-status-warning/5 p-4">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-status-warning">
        <AlertTriangle size={13} />
        {t("results.warnings")}
      </p>
      <ul className="space-y-1.5">
        {warnings.map((w, i) => (
          <li key={i} className="text-sm text-text-secondary">
            {w}
          </li>
        ))}
      </ul>
    </div>
  );
}
