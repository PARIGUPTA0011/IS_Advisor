import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Monitor, Moon, RefreshCw, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "../contexts/ThemeContext";
import { useAnalysisPrefs } from "../contexts/AnalysisPrefsContext";
import { useHealth } from "../hooks/useHealth";
import { SUPPORTED_LANGUAGE_CODES, persistLanguage, type LanguageCode } from "../i18n";
import { getSupportedLanguages, type ApiLanguage } from "../api/languages";

function SectionCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="glass-panel rounded-2xl p-5">
      <h2 className="mb-4 text-sm font-semibold text-text-primary">{title}</h2>
      {children}
    </div>
  );
}

const THEME_OPTIONS: { value: ThemePreference; icon: typeof Sun; labelKey: string }[] = [
  { value: "light", icon: Sun, labelKey: "settings.light" },
  { value: "dark", icon: Moon, labelKey: "settings.dark" },
  { value: "system", icon: Monitor, labelKey: "settings.system" },
];

export function Settings() {
  const { t, i18n } = useTranslation();
  const { preference, setPreference } = useTheme();
  const { topK, setTopK } = useAnalysisPrefs();
  const { status, data, retry } = useHealth();
  const [languages, setLanguages] = useState<ApiLanguage[]>([]);

  useEffect(() => {
    let cancelled = false;
    void getSupportedLanguages().then((items) => {
      if (!cancelled) setLanguages(items.filter((item) => SUPPORTED_LANGUAGE_CODES.includes(item.iso as LanguageCode)));
    }).catch(() => {
      if (!cancelled) setLanguages([]);
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="mx-auto max-w-2xl space-y-5 px-4 py-10 md:px-8">
      <h1 className="font-display text-3xl font-semibold text-text-primary">{t("settings.title")}</h1>

      <SectionCard title={t("settings.preferences") }>
        <div className="flex flex-col gap-6">
          <div>
            <p className="mb-3 text-xs font-medium uppercase tracking-[0.14em] text-text-muted">{t("settings.appearance")}</p>
            <div className="flex gap-2">
              {THEME_OPTIONS.map(({ value, icon: Icon, labelKey }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setPreference(value)}
                  className={`flex flex-1 flex-col items-center gap-2 rounded-xl border px-4 py-3 text-xs font-medium transition-colors ${
                    preference === value
                      ? "border-accent-primary bg-accent-primary/10 text-accent-primary"
                      : "border-border text-text-secondary hover:border-border-strong"
                  }`}
                >
                  <Icon size={18} />
                  {t(labelKey)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-3 block text-xs font-medium uppercase tracking-[0.14em] text-text-muted" htmlFor="settings-language">{t("settings.language")}</label>
            <select
              id="settings-language"
              value={i18n.language}
              onChange={(event) => {
                const code = event.target.value as LanguageCode;
                i18n.changeLanguage(code);
                persistLanguage(code);
              }}
              className="w-full rounded-xl border border-border bg-surface px-4 py-3 text-sm font-medium text-text-primary outline-none transition-colors focus:border-accent-primary"
            >
              {languages.map((lang) => (
                <option key={lang.iso} value={lang.iso}>
                  {lang.iso === "en" ? "English" : `${lang.native_name} (${lang.name})`}
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-text-secondary">
              <span>{t("settings.topK")}</span>
              <span className="font-semibold text-accent-primary">{topK} {t("settings.standards")}</span>
            </div>
            <input type="range" min={1} max={50} value={topK} onChange={(event) => setTopK(Number(event.target.value))} className="w-full accent-[var(--accent-primary)]" aria-label={t("settings.topK")} />
          </div>
        </div>
      </SectionCard>

      <div className={`rounded-2xl border p-5 ${status === "offline" ? "border-status-withdrawn/40 bg-status-withdrawn/5" : "border-status-current/30 bg-status-current/5"}`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">{t("settings.systemStatus")}</h2>
            <p className="mt-1 flex items-center gap-2 text-sm text-text-secondary">
              <span className={`size-2 rounded-full ${status === "online" ? "bg-status-current" : status === "offline" ? "bg-status-withdrawn" : "bg-status-warning"}`} />
              {status === "online" ? t("settings.connected") : status === "offline" ? t("settings.disconnected") : t("dashboard.checking")}
              {data && <span className="text-text-muted">· {t("settings.standardsLoaded", { count: data.standards_loaded })}</span>}
            </p>
            {status === "offline" && <p className="mt-2 text-xs text-text-muted">{t("settings.disconnectedHint")}</p>}
          </div>
          {status === "offline" && <button type="button" onClick={() => void retry()} className="inline-flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-sm font-medium text-text-primary hover:bg-surface-muted"><RefreshCw size={15} />{t("settings.retryConnection")}</button>}
        </div>
      </div>
    </div>
  );
}
