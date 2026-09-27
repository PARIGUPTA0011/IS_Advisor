import { API_BASE_URL, ApiError } from "./client";

export interface TenderHealthStandard {
  cited_as: string;
  is_number: string;
  title: string;
  status: string;
  replaced_by_is: string | null;
  successor_parts: string[];
  note: string | null;
}

export interface TenderHealthReport {
  total_items: number;
  items_with_citations: number;
  items_without_citations: number;
  unique_standards_cited: number;
  current_standards: number;
  outdated_standards: number;
  standards: TenderHealthStandard[];
  items_without_standards: string[];
}

export async function tenderHealth(
  file: File,
): Promise<TenderHealthReport> {
  const form = new FormData();
  form.append("file", file);

  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}/tender-health`, {
      method: "POST",
      body: form,
    });
  } catch {
    throw new ApiError(
      0,
      "Could not reach the IS-Advisor backend. Is it running?",
    );
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

  return (await response.json()) as TenderHealthReport;
}