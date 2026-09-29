import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import hi from "./hi.json";
import generated from "./generated.json";
import { translationFor } from "./indic";

// `generated.json` is machine-translated (NLLB, via scripts/generate via the
// project's own translator) for every key indic.ts/hi.json don't cover yet -
// see indic.ts's own comment on why those two are hand-written and the rest
// mostly are not. It is deliberately the WEAKEST layer: any hand-written key
// for the same path wins, so this only ever fills genuine gaps.
function deepMerge(base: unknown, override: unknown): unknown {
  if (
    base && override &&
    typeof base === "object" && typeof override === "object" &&
    !Array.isArray(base) && !Array.isArray(override)
  ) {
    const merged: Record<string, unknown> = { ...(base as Record<string, unknown>) };
    for (const [key, value] of Object.entries(override as Record<string, unknown>)) {
      // indic.ts's LocaleWords objects set unfilled fields to explicit
      // `undefined` (e.g. Kashmiri has no `w.appearance`), so `value` being
      // `undefined` here means "this language's hand-written layer doesn't
      // cover this key" - not "erase the machine-translated fallback".
      if (value === undefined) continue;
      merged[key] = key in merged ? deepMerge(merged[key], value) : value;
    }
    return merged;
  }
  return override;
}

function resourceFor(code: string): object {
  if (code === "en") return en;
  const handWritten = code === "hi" ? hi : translationFor(code as Parameters<typeof translationFor>[0]);
  const machineTranslated = (generated as Record<string, object>)[code];
  return machineTranslated ? (deepMerge(machineTranslated, handWritten) as object) : handWritten;
}

export const SUPPORTED_LANGUAGE_CODES = [
  "en", "as", "bn", "brx", "doi", "gu", "hi", "kn", "ks", "kok", "mai", "ml",
  "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd", "ta", "te", "ur", "ar",
  "de", "fr", "id", "ja", "ko", "fa", "pt", "ru", "es", "sw", "th", "vi", "zh",
] as const;

export type LanguageCode = (typeof SUPPORTED_LANGUAGE_CODES)[number];

const STORAGE_KEY = "isadvisor.language";
const warnedMissing = new Set<string>();

function englishText(key: string): string | undefined {
  return key.split(".").reduce<unknown>((value, part) => {
    if (value && typeof value === "object" && part in value) {
      return (value as Record<string, unknown>)[part];
    }
    return undefined;
  }, en) as string | undefined;
}

function readStoredLanguage(): LanguageCode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (SUPPORTED_LANGUAGE_CODES.includes(stored as LanguageCode)) return stored as LanguageCode;
  } catch {
    // localStorage unavailable - fall back to default
  }
  return "en";
}

export function persistLanguage(code: LanguageCode) {
  try {
    window.localStorage.setItem(STORAGE_KEY, code);
  } catch {
    // best-effort persistence only
  }
}

i18n.use(initReactI18next).use({
  type: "postProcessor",
  name: "warnOnEnglishFallback",
  process(value: string, key: string | string[], options: { lng?: string }) {
    const resourceKey = Array.isArray(key) ? key.join(".") : key;
    const language = String(options.lng ?? i18n.language).split("-")[0];
    if (language !== "en" && i18n.getResource(language, "translation", resourceKey) === undefined) {
      const warningKey = `${language}:${resourceKey}`;
      if (!warnedMissing.has(warningKey)) {
        warnedMissing.add(warningKey);
        console.warn(`[i18n] Missing ${language} translation for "${resourceKey}"; showing English fallback.`);
      }
    }
    return value;
  },
}).init({
  resources: Object.fromEntries(
    SUPPORTED_LANGUAGE_CODES.map((code) => [
      code,
      {
        translation: resourceFor(code),
      },
    ]),
  ),
  lng: readStoredLanguage(),
  fallbackLng: "en",
  postProcess: ["warnOnEnglishFallback"],
  parseMissingKeyHandler: (key) => englishText(key) ?? key.split(".").at(-1)?.replace(/([a-z])([A-Z])/g, "$1 $2") ?? key,
  interpolation: { escapeValue: false },
});

const RTL_LANGUAGES = new Set(["ar", "fa", "ks", "sd", "ur"]);
function updateDocumentLanguage(language: string) {
  const code = language.split("-")[0];
  document.documentElement.lang = code;
  document.documentElement.dir = RTL_LANGUAGES.has(code) ? "rtl" : "ltr";
}

updateDocumentLanguage(i18n.language);
i18n.on("languageChanged", updateDocumentLanguage);

export default i18n;
