import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LayoutGrid, Search, Settings as SettingsIcon } from "lucide-react";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";
import { LanguageSwitcher } from "./LanguageSwitcher";
import { SystemStatusPill } from "./SystemStatusPill";

const NAV_ITEMS = [
  { to: "/", label: "nav.dashboard", icon: LayoutGrid, end: true },
  { to: "/analyze", label: "nav.analyze", icon: Search, end: false },
  { to: "/settings", label: "nav.settings", icon: SettingsIcon, end: false },
];

export function AppLayout() {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-svh bg-bg text-text-primary">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-bg-elevated px-4 py-6 md:flex">
        <div className="mb-8 flex items-center gap-2.5 px-2">
          <Logo />
          <span className="font-display text-lg font-semibold tracking-tight">{t("app.name")}</span>
        </div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-accent-primary/10 text-accent-primary"
                    : "text-text-secondary hover:bg-surface-muted hover:text-text-primary"
                }`
              }
            >
              <Icon size={17} strokeWidth={2} />
              {t(label)}
            </NavLink>
          ))}
        </nav>
        <div className="px-2 pt-4">
          <SystemStatusPill />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b border-border bg-bg-elevated/80 px-4 py-3 backdrop-blur md:px-8">
          <div className="flex items-center gap-2 md:hidden">
            <Logo size={24} />
            <span className="font-display text-base font-semibold">{t("app.name")}</span>
          </div>
          <div className="hidden md:block" />
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
        </header>

        <main className="relative flex-1 overflow-y-auto">
          <Outlet />
        </main>

        <nav className="flex items-center justify-around border-t border-border bg-bg-elevated px-2 py-2 md:hidden">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 rounded-lg px-3 py-1.5 text-[11px] font-medium ${
                  isActive ? "text-accent-primary" : "text-text-muted"
                }`
              }
            >
              <Icon size={18} strokeWidth={2} />
              {t(label)}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
