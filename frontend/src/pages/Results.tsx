import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, FileSearch, RotateCcw } from "lucide-react";
import { ConfidenceMeter } from "../components/common/ConfidenceMeter";
import { EmptyState } from "../components/common/EmptyState";
import { RecommendationCard } from "../components/results/RecommendationCard";
import { EvidenceGrid } from "../components/results/EvidenceGrid";
import { WarningsBanner } from "../components/results/WarningsBanner";
import type { RecommendResponse } from "../types/api";

export function Results() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const result = (location.state as { result?: RecommendResponse } | null)?.result;

  if (!result) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16">
        <EmptyState
          icon={<FileSearch size={28} />}
          title={t("results.noRecommendations")}
          description="Start a new analysis from the Analyze page."
          action={
            <button
              type="button"
              onClick={() => navigate("/analyze")}
              className="mt-2 rounded-full bg-accent-primary px-4 py-2 text-sm font-semibold text-text-on-primary"
            >
              {t("results.newAnalysis")}
            </button>
          }
        />
      </div>
    );
  }

  const hasRecommendations = result.recommendations.length > 0;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 md:px-8">
      <button
        type="button"
        onClick={() => navigate("/analyze")}
        className="mb-4 flex items-center gap-1.5 text-xs font-medium text-text-muted transition-colors hover:text-text-primary"
      >
        <ArrowLeft size={14} />
        {t("results.newAnalysis")}
      </button>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass-panel rounded-2xl p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">{t("results.title")}</p>
        <p className="mt-1.5 text-sm text-text-secondary">"{result.query}"</p>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <ConfidenceMeter confidence={result.confidence} />
          <span className="text-xs text-text-muted">
            {result.recommendations.length} {t("results.recommendations").toLowerCase()} · {result.evidence.length}{" "}
            {t("results.evidenceRetrieved").toLowerCase()}
          </span>
        </div>
      </motion.div>

      <div className="mt-6 space-y-6">
        {result.warnings.length > 0 && <WarningsBanner warnings={result.warnings} />}

        <div>
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-text-muted">
            {t("results.recommendations")}
          </h2>
          {hasRecommendations ? (
            <div className="space-y-3">
              {result.recommendations.map((rec, i) => (
                <RecommendationCard
                  key={`${rec.standard_id}-${i}`}
                  recommendation={rec}
                  evidence={result.evidence}
                  relatedStandards={result.related_standards}
                  index={i}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              title={t("results.noRecommendations")}
              description={result.confidence === "insufficient_evidence" ? t("results.insufficientEvidence") : undefined}
              action={
                <button
                  type="button"
                  onClick={() => navigate("/analyze")}
                  className="mt-2 flex items-center gap-1.5 rounded-full bg-accent-primary px-4 py-2 text-sm font-semibold text-text-on-primary"
                >
                  <RotateCcw size={14} />
                  {t("results.newAnalysis")}
                </button>
              }
            />
          )}
        </div>

        <EvidenceGrid evidence={result.evidence} />
      </div>
    </div>
  );
}
