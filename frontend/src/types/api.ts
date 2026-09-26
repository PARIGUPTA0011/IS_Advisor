/**
 * Types mirror api/main.py's Pydantic models EXACTLY. If the backend schema
 * changes, update this file to match - never invent fields here that the
 * backend doesn't actually return.
 */

export interface RecommendRequest {
  query: string;
  top_k?: number;
  language?: string | null;
}

export type Confidence = "high" | "medium" | "low" | "insufficient_evidence" | "parse_error" | "unknown";

export type StandardStatus = "current" | "withdrawn" | null;

/** One KG relationship type, exactly as Neo4j/rag/kg_client.py produces it. */
export type Relationship = "REFERENCES" | "REFERENCED_BY" | "REPLACED_BY" | "REPLACES";

/** One relevance tier, exactly as Semantic_Analysis/is_advisor/search.py computes it. */
export type Tier = "Highly relevant" | "Related" | "Possibly relevant";

export interface RecommendationOut {
  standard_id: string;
  status: StandardStatus;
  reason: string;
  evidence_tag: string | null;
}

export interface RelatedStandardOut {
  standard_id: string;
  relationship: string;
  related_to: string;
  reason: string | null;
}

export interface EvidenceOut {
  tag: string;
  standard_id: string;
  title: string | null;
  status: StandardStatus;
  score: number;
  why: string | null;
  tier: string | null;
}

export interface RecommendResponse {
  query: string;
  recommendations: RecommendationOut[];
  related_standards: RelatedStandardOut[];
  evidence: EvidenceOut[];
  warnings: string[];
  confidence: Confidence;
}

export interface HealthResponse {
  status: string;
  standards_loaded: number;
}

/** Shape of a FastAPI HTTPException error body: {"detail": "..."} */
export interface ApiErrorBody {
  detail: string;
}
