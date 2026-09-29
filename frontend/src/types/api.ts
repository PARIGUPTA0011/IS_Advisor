/**
 * Types mirror api/main.py's Pydantic models EXACTLY. If the backend schema
 * changes, update this file to match - never invent fields here that the
 * backend doesn't actually return.
 */

export interface RecommendRequest {
  query: string;
  top_k?: number;
  // Omit this. The backend detects the query's language on its own, the same
  // way run_query.py does when --lang is not given - forcing a value here
  // (e.g. to whatever the UI's own display language happens to be) overrides
  // that detection and is what broke non-English queries previously. Kept
  // optional, not deleted, in case a future explicit override control is
  // added deliberately.
  language?: string | null;
}

export type Confidence = "high" | "medium" | "low" | "insufficient_evidence" | "parse_error" | "unknown";

export type StandardStatus = "current" | "withdrawn" | null;

/** One KG relationship type, exactly as Neo4j/rag/kg_client.py produces it. */
export type Relationship =
  | "REFERENCES"
  | "REFERENCED_BY"
  | "REPLACED_BY"
  | "REPLACES"
  | "NORMATIVELY_REFERENCES";

/** One relevance tier, exactly as Semantic_Analysis/is_advisor/search.py computes it. */
export type Tier = "Highly relevant" | "Related" | "Possibly relevant";

export interface RecommendationOut {
  standard_id: string;
  status: StandardStatus;
  reason: string;
  evidence_tag: string | null;
  // Present only for a non-English query. standard_id is never translated (it
  // is an identifier); reason_localized/status_localized sit beside the
  // English reason/status, never replacing them.
  reason_localized?: string | null;
  status_localized?: string | null;
}

export interface RelatedStandardOut {
  standard_id: string;
  relationship: string;
  related_to: string;
  reason: string | null;
  // reason_localized sits beside reason; title/status are looked up from the
  // dataset by rag/pipeline.py so a related standard can be shown with its
  // real title and current/withdrawn status, not just its bare number.
  reason_localized?: string | null;
  title?: string | null;
  status?: StandardStatus;
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

export interface KnowledgeGraphNode {
  id: string;
  standard_id: string;
  title: string | null;
  status: StandardStatus;
  retrieved: boolean;
}

export interface KnowledgeGraphEdge {
  source: string;
  target: string;
  relationship: Relationship;
}

export interface KnowledgeGraphOut {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
}

/** What multilingual.Localizer.describe() reports about the answer's language.
 * `rtl` and `script` come from the backend's own script table
 * (multilingual/languages.py) rather than being guessed again here, so the
 * frontend never needs its own copy of "which scripts read right-to-left". */
export interface LanguageInfo {
  code: string;
  name: string;
  native_name: string;
  script: string;
  rtl: boolean;
  tier: "first_class" | "best_effort";
  localized: boolean;
  titles_translated: boolean;
  note: string;
}

export interface RecommendResponse {
  query: string;
  recommendations: RecommendationOut[];
  related_standards: RelatedStandardOut[];
  evidence: EvidenceOut[];
  knowledge_graph: KnowledgeGraphOut;
  warnings: string[];
  confidence: Confidence;
  // All optional and absent/null for an English query, so an existing caller
  // that ignores them sees exactly the response it saw before.
  query_english?: string | null;       // what retrieval and the LLM actually saw
  language?: LanguageInfo | null;      // which language was detected, and how
  warnings_localized?: string[];       // same order/length as warnings, when localized
  unsupported_spec_terms?: string[];
  detection?: Record<string, unknown> | null;
  translation?: Record<string, unknown> | null;
}

/** "not_started" before warm-up has run, "loading" while the translation
 * model is loading in the background (server already accepting requests),
 * "ready" once it can translate, "failed" if it could not, "disabled" if
 * IS_ADVISOR_TRANSLATE=0. English queries never wait on this - detection
 * short-circuits before the translator is touched for text that already is
 * English. */
export interface WarmupStatus {
  state: "not_started" | "loading" | "ready" | "failed" | "disabled";
  elapsed_s: number | null;
  detail: string;
}

export interface HealthResponse {
  status: string;
  standards_loaded: number;
  warmup?: WarmupStatus;
  speech_warmup?: WarmupStatus;
  translation?: Record<string, unknown>;
  graph?: Record<string, unknown>;
}

/** Mirrors api/main.py's TranscribeResponse, which mirrors speech/transcribe.py's
 * Transcript.to_dict() plus language_iso/language_name for the frontend's
 * convenience - see api/main.py::transcribe_audio for why those two exist. */
export interface TranscribeResponse {
  text: string;
  raw_text: string;
  language: string;
  language_iso: string | null;
  language_name: string | null;
  whisper_language: string | null;
  whisper_confidence: number | null;
  detected_script: string;
  detection_method: string;
  language_mismatch: string;
  duration: number | null;
  notation_changes: [string, string][];
  engine: string;
  note: string;
}

/** Shape of a FastAPI HTTPException error body: {"detail": "..."} */
export interface ApiErrorBody {
  detail: string;
}
