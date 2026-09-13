import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import hi from "./hi.json";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English", apiName: "English" },
  { code: "hi", label: "हिन्दी", apiName: "Hindi" },
] as const;

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]["code"];

const STORAGE_KEY = "isadvisor.language";

function readStoredLanguage(): LanguageCode {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (SUPPORTED_LANGUAGES.some((l) => l.code === stored)) return stored as LanguageCode;
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

export function apiLanguageName(code: string): string {
  return SUPPORTED_LANGUAGES.find((l) => l.code === code)?.apiName ?? "English";
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    hi: { translation: hi },
  },
  lng: readStoredLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
