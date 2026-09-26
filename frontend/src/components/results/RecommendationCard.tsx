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
}

export function RecommendationCard({ recommendation, evidence, relatedStandards, index }: Props) {
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
        className="flex w-full items-start justify-between gap-4 p-5 text-left"
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
                  return (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs"
                      title={rel.reason ?? undefined}
                    >
                      <span className="text-text-muted">{rel.relationship.replace(/_/g, " ").toLowerCase()}</span>
                      <span className="font-medium text-text-primary">{other}</span>
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
