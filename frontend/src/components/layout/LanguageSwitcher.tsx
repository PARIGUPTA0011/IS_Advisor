import { useState } from "react";
import { Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES, persistLanguage, type LanguageCode } from "../../i18n";

export function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const current = SUPPORTED_LANGUAGES.find((l) => l.code === i18n.language) ?? SUPPORTED_LANGUAGES[0];

  const select = (code: LanguageCode) => {
    i18n.changeLanguage(code);
    persistLanguage(code);
    setOpen(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-full border border-border bg-surface-muted px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
      >
        <Globe size={13} />
        {current.label}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-36 overflow-hidden rounded-xl border border-border bg-surface shadow-[var(--shadow-card)]">
            {SUPPORTED_LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                type="button"
                onClick={() => select(lang.code)}
                className={`block w-full px-3 py-2 text-left text-sm transition-colors hover:bg-surface-muted ${
                  lang.code === current.code ? "text-accent-primary font-medium" : "text-text-secondary"
                }`}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
