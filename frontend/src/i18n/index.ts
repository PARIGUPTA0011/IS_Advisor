import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import hi from "./hi.json";
import { translationFor } from "./indic";

export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English", apiName: "English" },
  { code: "as", label: "অসমীয়া", apiName: "Assamese" },
  { code: "bn", label: "বাংলা", apiName: "Bengali" },
  { code: "brx", label: "बड़ो", apiName: "Bodo" },
  { code: "doi", label: "डोगरी", apiName: "Dogri" },
  { code: "gu", label: "ગુજરાતી", apiName: "Gujarati" },
  { code: "hi", label: "हिन्दी", apiName: "Hindi" },
  { code: "kn", label: "ಕನ್ನಡ", apiName: "Kannada" },
  { code: "ks", label: "कॉशुर / کٲشُر", apiName: "Kashmiri" },
  { code: "kok", label: "कोंकणी", apiName: "Konkani" },
  { code: "mai", label: "मैथिली", apiName: "Maithili" },
  { code: "ml", label: "മലയാളം", apiName: "Malayalam" },
  { code: "mni", label: "মৈতৈলোন্", apiName: "Manipuri" },
  { code: "mr", label: "मराठी", apiName: "Marathi" },
  { code: "ne", label: "नेपाली", apiName: "Nepali" },
  { code: "or", label: "ଓଡ଼ିଆ", apiName: "Odia" },
  { code: "pa", label: "ਪੰਜਾਬੀ", apiName: "Punjabi" },
  { code: "sa", label: "संस्कृतम्", apiName: "Sanskrit" },
  { code: "sat", label: "ᱥᱟᱱᱛᱟᱲᱤ", apiName: "Santali" },
  { code: "sd", label: "सिन्धी / سنڌي", apiName: "Sindhi" },
  { code: "ta", label: "தமிழ்", apiName: "Tamil" },
  { code: "te", label: "తెలుగు", apiName: "Telugu" },
  { code: "ur", label: "اُردُو", apiName: "Urdu" },
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
  resources: Object.fromEntries(
    SUPPORTED_LANGUAGES.map(({ code }) => [
      code,
      {
        translation: code === "en" ? en : code === "hi" ? hi : translationFor(code),
      },
    ]),
  ),
  lng: readStoredLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
