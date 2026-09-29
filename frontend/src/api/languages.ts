import { apiFetch } from "./client";

export interface ApiLanguage {
  code: string;
  name: string;
  native_name: string;
  script: string;
  iso: string;
}

interface LanguageResponse {
  first_class: ApiLanguage[];
  best_effort: ApiLanguage[];
}

export async function getSupportedLanguages(): Promise<ApiLanguage[]> {
  const response = await apiFetch<LanguageResponse>("/languages");
  return [...response.first_class, ...response.best_effort].sort((left, right) => {
    if (left.iso === "en") return -1;
    if (right.iso === "en") return 1;
    return left.name.localeCompare(right.name, "en");
  });
}