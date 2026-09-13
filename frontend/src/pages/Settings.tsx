import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Info, Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "../contexts/ThemeContext";
import { useAnalysisPrefs } from "../contexts/AnalysisPrefsContext";
import { useHealth } from "../hooks/useHealth";
import { SUPPORTED_LANGUAGES, persistLanguage, type LanguageCode } from "../i18n";

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
  const { status, data } = useHealth();

  return (
    <div className="mx-auto max-w-2xl space-y-5 px-4 py-10 md:px-8">
      <h1 className="font-display text-3xl font-semibold text-text-primary">{t("settings.title")}</h1>

      <SectionCard title={t("settings.appearance")}>
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
      </SectionCard>

      <SectionCard title={t("settings.language")}>
        <div className="flex gap-2">
          {SUPPORTED_LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              type="button"
              onClick={() => {
                i18n.changeLanguage(lang.code);
                persistLanguage(lang.code as LanguageCode);
              }}
              className={`flex-1 rounded-xl border px-4 py-3 text-sm font-medium transition-colors ${
                i18n.language === lang.code
                  ? "border-accent-primary bg-accent-primary/10 text-accent-primary"
                  : "border-border text-text-secondary hover:border-border-strong"
              }`}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </SectionCard>

      <SectionCard title={t("settings.preferences")}>
        <label className="flex items-center justify-between gap-4 text-sm text-text-secondary">
          {t("settings.topK")}
          <input
            type="number"
            min={1}
            max={50}
            value={topK}
            onChange={(e) => setTopK(Math.min(50, Math.max(1, Number(e.target.value) || 1)))}
            className="w-20 rounded-lg border border-border bg-surface px-3 py-1.5 text-right text-sm text-text-primary focus:border-accent-primary focus:outline-none"
          />
        </label>
      </SectionCard>

      <SectionCard title={t("settings.systemStatus")}>
        <div className="flex items-center justify-between text-sm">
          <span className="flex items-center gap-2 text-text-secondary">
            <span
              className={`h-2 w-2 rounded-full ${
                status === "online" ? "bg-status-current" : status === "offline" ? "bg-status-withdrawn" : "bg-status-warning"
              }`}
            />
            {status === "online" ? t("settings.backendOnline") : status === "offline" ? t("settings.backendOffline") : t("dashboard.checking")}
          </span>
          {data && <span className="text-text-muted">{t("settings.standardsLoaded", { count: data.standards_loaded })}</span>}
        </div>
      </SectionCard>

      <SectionCard title={t("settings.about")}>
        <p className="flex items-start gap-2 text-sm text-text-secondary">
          <Info size={16} className="mt-0.5 shrink-0 text-text-muted" />
          {t("settings.aboutBody")}
        </p>
      </SectionCard>
    </div>
  );
}
