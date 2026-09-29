import i18n from "../i18n";
import type { ApiErrorBody } from "../types/api";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// A cold translation-model load now happens once, in the background, at
// server startup (see api/main.py's lifespan + multilingual/translate.py::
// warm_up) - not inside a user's request any more. A normal request after
// warm-up measures at a few seconds even on a slow machine. This timeout is
// a safety margin for genuinely unusual cases (a very slow LLM API response,
// or a request that lands in the rare window before warm-up finishes), not
// the primary defence against a cold model load - useTranslationWarmup.ts and
// WarmupBanner.tsx are.
export const REQUEST_TIMEOUT_MS = 180_000;

// How long the honest-error-message side-check (below) is allowed to take.
// Short on purpose: it exists to make a timeout message accurate, and taking
// nearly as long as the original timeout to find that out would defeat it.
const HEALTH_CHECK_TIMEOUT_MS = 5_000;

export function withTimeout(init: RequestInit = {}, timeoutMs: number = REQUEST_TIMEOUT_MS): RequestInit {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), timeoutMs);
  return { ...init, signal: controller.signal };
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    if (body?.detail) return body.detail;
  } catch {
    // response wasn't JSON - fall through to a generic message
  }
  return i18n.t("errors.requestFailed", { status: response.status });
}

/** Shared by every direct (non-apiFetch) fetch caller - recommendDocument and
 * transcribeAudio both do their own fetch (they send FormData, not JSON), but
 * should report failures identically to apiFetch rather than each keeping its
 * own copy of this logic. */
export async function readErrorFrom(response: Response): Promise<string> {
  return parseErrorDetail(response);
}

/**
 * A timeout on its own does not say WHY the server was slow, and a generic
 * "try again" message is wrong to show if the real cause is, for instance,
 * the translation model still loading - the user needs to know to wait
 * longer, not that something is broken. This asks the server's own current
 * state (best-effort, short-timeout, never throws) so the message the user
 * sees reflects what is actually true right now instead of a guess made once
 * at build time.
 */
export async function describeTimeout(): Promise<string> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, withTimeout({}, HEALTH_CHECK_TIMEOUT_MS));
    if (!response.ok) return i18n.t("errors.timeoutGeneric");
    const health = await response.json();
    const state = health?.warmup?.state;
    if (state === "loading" || state === "not_started") return i18n.t("errors.timeoutWarmingUp");
    if (state === "failed") return i18n.t("errors.timeoutTranslationFailed");
    return i18n.t("errors.timeoutGeneric");
  } catch {
    // The health check itself timed out or failed - the server may be
    // overloaded or down, which the generic message already covers honestly.
    return i18n.t("errors.timeoutGeneric");
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, withTimeout(init));
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(0, await describeTimeout());
    }
    throw new ApiError(0, i18n.t("errors.unreachable"));
  }
  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response));
  }
  return (await response.json()) as T;
}
