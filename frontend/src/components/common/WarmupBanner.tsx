import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { useTranslationWarmup } from "../../hooks/useTranslationWarmup";

/**
 * Shown while the backend's translation model is still loading (see
 * useTranslationWarmup.ts for why this exists). Renders nothing once ready,
 * once failed (a failure is reported honestly elsewhere - see the request
 * error path in api/client.ts - not hidden behind a banner that never
 * clears), or if translation is disabled outright.
 */
export function WarmupBanner() {
  const { t } = useTranslation();
  const { isPreparing } = useTranslationWarmup();

  if (!isPreparing) return null;

  return (
    <div className="mb-4 rounded-xl border border-accent-primary/20 bg-accent-primary/5 px-4 py-2.5 text-xs text-text-secondary" role="status" aria-live="polite">
      <div className="flex items-center gap-2">
        <Loader2 size={14} className="shrink-0 animate-spin text-accent-primary" />
        <span>{t("warmup.preparing")}</span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-accent-primary/10" aria-hidden="true">
        <div className="h-full w-1/3 animate-[warmup-progress_1.5s_ease-in-out_infinite] rounded-full bg-accent-primary" />
      </div>
    </div>
  );
}
