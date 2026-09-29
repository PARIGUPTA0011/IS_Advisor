import { useState } from "react";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import { ChevronDown, Sparkles } from "lucide-react";
import { StatusBadge } from "../common/StatusBadge";
import { TierBadge } from "../common/TierBadge";
import type { EvidenceOut, RecommendationOut, RelatedStandardOut } from "../../types/api";
import { findEvidenceForRecommendation } from "../../utils/evidence";

interface Props {
  recommendation: RecommendationOut;
  evidence: EvidenceOut[];
  relatedStandards: RelatedStandardOut[];
  index: number;
  /** True when the response's detected language reads right-to-left (Urdu,
   * Sindhi, Kashmiri, Arabic, Persian) - applied only to the localized prose,
   * never to the standard_id/title, which stay English and left-to-right. */
  rtl?: boolean;
}

export function RecommendationCard({ recommendation, evidence, relatedStandards, index, rtl }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(index === 0);

  const matchedEvidence = findEvidenceForRecommendation(recommendation, evidence);
  const related = relatedStandards.filter(
    (r) => r.standard_id === recommendation.standard_id || r.related_to === recommendation.standard_id,
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06 }}
      className="glass-panel overflow-hidden rounded-2xl"
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start justify-between gap-4 p-5 text-start"
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-lg font-semibold text-text-primary">{recommendation.standard_id}</h3>
            <StatusBadge status={recommendation.status} />
            {matchedEvidence && <TierBadge tier={matchedEvidence.tier} />}
          </div>
          {matchedEvidence?.title && <p className="mt-1 text-sm text-text-secondary">{matchedEvidence.title}</p>}
        </div>
        <ChevronDown
          size={18}
          className={`mt-1 shrink-0 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      {expanded && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          transition={{ duration: 0.25 }}
          className="space-y-4 border-t border-border px-5 pb-5 pt-4"
        >
          <div>
            <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-accent-primary">
              <Sparkles size={12} />
              {t("results.whyThisApplies")}
            </p>
            <p className="text-sm text-text-secondary">{recommendation.reason}</p>
            {/* reason_localized is only present for a non-English query and is
                machine translation, shown beside the English reason rather
                than replacing it - see rag/pipeline.py::localise_response. */}
            {recommendation.reason_localized && recommendation.reason_localized !== recommendation.reason && (
              <p className="mt-1 text-sm text-text-primary" dir={rtl ? "rtl" : undefined}>
                {recommendation.reason_localized}
              </p>
            )}
          </div>

          {matchedEvidence && (
            <div className="flex flex-wrap items-center gap-4 rounded-xl bg-surface-muted px-4 py-3 text-xs text-text-muted">
              <span>
                {t("results.score")}: <strong className="text-text-primary">{(matchedEvidence.score * 100).toFixed(0)}%</strong>
              </span>
              {matchedEvidence.why && <span className="text-text-secondary">{matchedEvidence.why}</span>}
            </div>
          )}

          {related.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                {t("results.relatedStandards")}
              </p>
              <div className="flex flex-wrap gap-2">
                {related.map((rel, i) => {
                  const other = rel.standard_id === recommendation.standard_id ? rel.related_to : rel.standard_id;
                  // The tooltip prefers the localized reason so it reads in
                  // the same language as the rest of the answer; English is
                  // still what a screen reader falls back to if there isn't one.
                  const tooltip = rel.reason_localized ?? rel.reason ?? undefined;
                  return (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs"
                      title={tooltip}
                    >
                      <span className="text-text-muted">{rel.relationship.replace(/_/g, " ").toLowerCase()}</span>
                      <span className="font-medium text-text-primary">{other}</span>
                      {/* rel.title is the standard's own title, looked up from
                          the dataset (rag/kg_editions.py) - previously this
                          pill only ever showed the bare number. */}
                      {rel.title && <span className="text-text-muted">· {rel.title}</span>}
                      {rel.status === "withdrawn" && (
                        <span className="text-status-withdrawn">({t("results.status.withdrawn")})</span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}
