import { useTranslation } from "react-i18next";
import type { StandardStatus } from "../../types/api";

export function StatusBadge({ status }: { status: StandardStatus }) {
  const { t } = useTranslation();
  if (!status) return null;

  const isCurrent = status === "current";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
        isCurrent
          ? "bg-status-current/10 text-status-current"
          : "bg-status-withdrawn/10 text-status-withdrawn"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${isCurrent ? "bg-status-current" : "bg-status-withdrawn"}`} />
      {isCurrent ? t("results.status.current") : t("results.status.withdrawn")}
    </span>
  );
}
