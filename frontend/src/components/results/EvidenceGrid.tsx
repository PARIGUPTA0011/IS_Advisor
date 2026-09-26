import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { EvidenceOut, RecommendationOut } from "../../types/api";

interface Props {
  evidence: EvidenceOut[];
  recommendations: RecommendationOut[];
}

export function EvidenceGrid({ evidence, recommendations }: Props) {
  const { t } = useTranslation();
  if (evidence.length === 0) return null;

  const recommendedIds = new Set(recommendations.map((recommendation) => recommendation.standard_id));

  return (
    <section aria-labelledby="retrieved-evidence-heading">
      <div className="mb-3">
        <h2 id="retrieved-evidence-heading" className="text-xs font-semibold uppercase tracking-wide text-text-muted">
          {t("results.evidenceRetrieved")}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-text-muted">
          {t("results.evidenceSubtitle", {
            defaultValue: "All standards considered during retrieval, including ones not recommended.",
          })}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {evidence.map((evidenceItem) => (
          <EvidenceCard
            key={evidenceItem.tag}
            evidence={evidenceItem}
            isRecommended={recommendedIds.has(evidenceItem.standard_id)}
          />
        ))}
      </div>
    </section>
  );
}

function EvidenceCard({ evidence, isRecommended }: { evidence: EvidenceOut; isRecommended: boolean }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const hasLongContent = Boolean(evidence.title && evidence.title.length > 100);

  return (
    <article className="glass-panel rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="break-words text-sm font-semibold leading-snug text-text-primary">{evidence.standard_id}</p>
          {isRecommended && (
            <span className="mt-2 inline-flex rounded-full border border-accent-primary/25 bg-accent-primary/10 px-2 py-0.5 text-[10px] font-medium text-accent-primary">
              {t("results.alsoRecommended", { defaultValue: "Also recommended" })}
            </span>
          )}
        </div>
        <span className="shrink-0 text-xs font-medium text-text-muted">{(evidence.score * 100).toFixed(0)}%</span>
      </div>

      {evidence.title && (
        <p className={`mt-2 break-words text-xs leading-relaxed text-text-secondary ${expanded ? "" : "line-clamp-3"}`}>
          {evidence.title}
        </p>
      )}

      {evidence.why && (
        <p className="mt-3 rounded-lg bg-surface-muted px-3 py-2 text-xs leading-relaxed text-text-muted">
          <span className="font-medium text-text-secondary">
            {t("results.retrievalReason", { defaultValue: "Why it appeared" })}: 
          </span>
          {evidence.why}
        </p>
      )}

      {hasLongContent && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-2 text-xs font-medium text-accent-primary hover:underline"
        >
          {expanded ? t("common.showLess", { defaultValue: "Show less" }) : t("common.showMore", { defaultValue: "Show more" })}
        </button>
      )}
    </article>
  );
}
