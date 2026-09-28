import { API_BASE_URL, ApiError } from "./client";
import type { TranscribeResponse } from "../types/api";

/**
 * Send a recorded audio clip to the speech/ edge layer and get back a
 * transcript. Deliberately its own call, not folded into recommend(): the UI
 * shows what was heard before it commits to a retrieval + LLM call on it,
 * mirroring "print the transcript before the results" in run_query.py and
 * Semantic_Analysis/03_search.py.
 *
 * `language` is normally omitted on purpose - see useSpeechToText.ts for why
 * forcing it here would work against the point of listening to the audio.
 */
export async function transcribeAudio(
  blob: Blob,
  options: { language?: string | null; filename?: string } = {},
): Promise<TranscribeResponse> {
  const form = new FormData();
  // The backend also infers the format from Content-Type when the filename
  // carries no real extension (a MediaRecorder Blob is usually just "blob"),
  // so this name only needs to exist, not be exact.
  const extension = blob.type.includes("ogg") ? "ogg" : blob.type.includes("mp4") ? "m4a" : "webm";
  form.append("file", blob, options.filename ?? `recording.${extension}`);

  const params = new URLSearchParams();
  if (options.language) params.set("language", options.language);
  const query = params.toString() ? `?${params.toString()}` : "";

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/transcribe${query}`, {
      method: "POST",
      body: form,
    });
  } catch {
    throw new ApiError(0, "Could not reach the IS-Advisor backend. Is it running?");
  }
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // not JSON, keep generic message
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as TranscribeResponse;
}
