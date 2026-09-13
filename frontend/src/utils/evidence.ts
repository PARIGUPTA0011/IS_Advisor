import type { EvidenceOut, RecommendationOut } from "../types/api";

/**
 * The LLM is asked to copy the exact [N] evidence_tag, but it sometimes
 * returns something looser (observed: the literal string "RETRIEVED
 * EVIDENCE" instead of "[2]"). Try the tag first, then fall back to matching
 * by standard_id, which is always reliable since the grounding validator
 * already guarantees every recommended standard_id exists in evidence.
 */
export function findEvidenceForRecommendation(
  rec: RecommendationOut,
  evidence: EvidenceOut[],
): EvidenceOut | null {
  if (rec.evidence_tag) {
    const byTag = evidence.find((e) => e.tag === rec.evidence_tag);
    if (byTag) return byTag;
  }
  return evidence.find((e) => e.standard_id === rec.standard_id) ?? null;
}
