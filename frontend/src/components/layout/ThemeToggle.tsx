import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "../../contexts/ThemeContext";

const OPTIONS: { value: ThemePreference; icon: typeof Sun }[] = [
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
  { value: "system", icon: Monitor },
];

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  return (
    <label className="flex items-center gap-2 rounded-xl border border-border bg-surface-muted px-2.5 py-1.5 text-xs text-text-secondary">
      <span className="sr-only">Theme</span>
      <select
        value={preference}
        onChange={(event) => setPreference(event.target.value as ThemePreference)}
        aria-label="Theme"
        className="bg-transparent font-medium text-text-primary outline-none"
      >
        {OPTIONS.map(({ value }) => (
          <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>
        ))}
      </select>
    </label>
  );
}
