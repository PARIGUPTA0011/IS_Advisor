import i18n from "../i18n";
import { apiFetch, API_BASE_URL, ApiError, describeTimeout, readErrorFrom, withTimeout } from "./client";
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
    response = await fetch(
      `${API_BASE_URL}/recommend/document${query}`,
      withTimeout({ method: "POST", body: form }),
    );
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, await describeTimeout());
    }
    throw new ApiError(0, i18n.t("errors.unreachable"));
  }
  if (!response.ok) {
    throw new ApiError(response.status, await readErrorFrom(response));
  }
  return (await response.json()) as RecommendResponse;
}
