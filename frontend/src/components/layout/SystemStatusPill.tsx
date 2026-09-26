import { useTranslation } from "react-i18next";
import { useHealth } from "../../hooks/useHealth";

export function SystemStatusPill() {
  const { t } = useTranslation();
  const { status } = useHealth();

  const label =
    status === "loading" ? t("dashboard.checking") : status === "online" ? t("settings.backendOnline") : t("settings.backendOffline");

  const dotColor = status === "online" ? "bg-status-current" : status === "offline" ? "bg-status-withdrawn" : "bg-status-warning";

  return (
    <div className="flex items-center gap-2 rounded-full border border-border bg-surface-muted px-3 py-1.5 text-xs font-medium text-text-secondary">
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor} ${status === "loading" ? "animate-pulse" : ""}`} />
      {label}
    </div>
  );
}
