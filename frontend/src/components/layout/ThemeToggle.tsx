import { Monitor, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme, type ThemePreference } from "../../contexts/ThemeContext";

const OPTIONS: { value: ThemePreference; icon: typeof Sun; labelKey: string }[] = [
  { value: "light", icon: Sun, labelKey: "settings.light" },
  { value: "dark", icon: Moon, labelKey: "settings.dark" },
  { value: "system", icon: Monitor, labelKey: "settings.system" },
];

export function ThemeToggle() {
  const { t } = useTranslation();
  const { preference, setPreference } = useTheme();

  return (
    <label className="flex items-center gap-2 rounded-xl border border-border bg-surface-muted px-2.5 py-1.5 text-xs text-text-secondary">
      <span className="sr-only">{t("settings.appearance")}</span>
      <select
        value={preference}
        onChange={(event) => setPreference(event.target.value as ThemePreference)}
        aria-label={t("settings.appearance")}
        className="bg-transparent font-medium text-text-primary outline-none"
      >
        {OPTIONS.map(({ value, labelKey }) => (
          <option key={value} value={value}>{t(labelKey)}</option>
        ))}
      </select>
    </label>
  );
}
