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
    <div className="flex items-center gap-0.5 rounded-full border border-border bg-surface-muted p-0.5">
      {OPTIONS.map(({ value, icon: Icon }) => (
        <button
          key={value}
          type="button"
          aria-label={`${value} theme`}
          onClick={() => setPreference(value)}
          className={`flex h-7 w-7 items-center justify-center rounded-full transition-colors ${
            preference === value
              ? "bg-accent-primary text-text-on-primary"
              : "text-text-muted hover:text-text-primary"
          }`}
        >
          <Icon size={14} strokeWidth={2} />
        </button>
      ))}
    </div>
  );
}
