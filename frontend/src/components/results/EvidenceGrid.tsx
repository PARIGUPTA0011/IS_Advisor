import { useTranslation } from "react-i18next";
import { TierBadge } from "../common/TierBadge";
import { StatusBadge } from "../common/StatusBadge";
import type { EvidenceOut } from "../../types/api";

export function EvidenceGrid({ evidence }: { evidence: EvidenceOut[] }) {
  const { t } = useTranslation();
  if (evidence.length === 0) return null;

  return (
    <div>
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
        {t("results.evidenceRetrieved")}
      </h2>
      <div className="grid gap-2 sm:grid-cols-2">
        {evidence.map((e) => (
          <div key={e.tag} className="glass-panel rounded-xl p-3.5">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-medium text-text-primary">{e.standard_id}</p>
              <span className="shrink-0 text-xs text-text-muted">{(e.score * 100).toFixed(0)}%</span>
            </div>
            {e.title && <p className="mt-0.5 line-clamp-1 text-xs text-text-secondary">{e.title}</p>}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <StatusBadge status={e.status} />
              <TierBadge tier={e.tier} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
