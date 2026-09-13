import { apiFetch, API_BASE_URL, ApiError } from "./client";
import type { RecommendRequest, RecommendResponse } from "../types/api";

export async function recommend(req: RecommendRequest): Promise<RecommendResponse> {
  return apiFetch<RecommendResponse>("/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export async function recommendDocument(
  file: File,
  options: { top_k?: number; language?: string | null } = {},
): Promise<RecommendResponse> {
  const form = new FormData();
  form.append("file", file);

  const params = new URLSearchParams();
  if (options.top_k) params.set("top_k", String(options.top_k));
  if (options.language) params.set("language", options.language);
  const query = params.toString() ? `?${params.toString()}` : "";

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/recommend/document${query}`, {
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
  return (await response.json()) as RecommendResponse;
}
