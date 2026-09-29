import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Globe, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { getSupportedLanguages, type ApiLanguage } from "../../api/languages";
import { SUPPORTED_LANGUAGE_CODES, persistLanguage, type LanguageCode } from "../../i18n";

/**
 * This controls only the website's own interface text (nav labels, buttons,
 * headings) via i18next - it must never be sent to the backend as the answer
 * language, which the backend always detects from the actual query. See
 * Analyze.tsx / Dashboard.tsx, which no longer read this value at all.
 *
 * Previously all 23 languages rendered but only the last ~5 were clickable.
 * The panel had no height limit and no scroll container, so on most viewports
 * it extended past the header's own box into the page content below; that
 * content, painted after the header in normal document flow, intercepted
 * clicks on whichever entries it happened to overlap. Rendering the panel
 * through a portal at a `position: fixed` coordinate anchored to the trigger
 * button - the same approach headless UI libraries use - removes it from the
 * header's layout entirely, so no ancestor's overflow, backdrop-filter
 * stacking context, or sibling z-index can clip or shadow it, on any page.
 */
export function LanguageSwitcher() {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [languages, setLanguages] = useState<ApiLanguage[]>([]);
  const [coords, setCoords] = useState({ top: 0, right: 0 });

  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    let cancelled = false;
    void getSupportedLanguages().then((items) => {
      if (!cancelled) setLanguages(items.filter((item) => SUPPORTED_LANGUAGE_CODES.includes(item.iso as LanguageCode)));
    }).catch(() => {
      if (!cancelled) setLanguages([]);
    });
    return () => { cancelled = true; };
  }, []);

  const current = languages.find((language) => language.iso === i18n.language);
  const visibleLanguages = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return languages.filter((language) =>
      !needle || language.name.toLocaleLowerCase().includes(needle) || language.native_name.toLocaleLowerCase().includes(needle),
    );
  }, [languages, query]);
  const label = (language: ApiLanguage) => language.iso === "en" ? "English" : `${language.native_name} (${language.name})`;

  const reposition = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setCoords({ top: rect.bottom + 8, right: window.innerWidth - rect.right });
  }, []);

  const openMenu = () => {
    reposition();
    setQuery("");
    setOpen(true);
  };

  const closeMenu = (returnFocus = false) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

  const select = (code: string) => {
    if (!SUPPORTED_LANGUAGE_CODES.includes(code as LanguageCode)) return;
    i18n.changeLanguage(code);
    persistLanguage(code as LanguageCode);
    closeMenu(true);
  };

  // The panel's position is computed from the trigger's on-screen rect (not
  // CSS alone), so it has to be recomputed if the page scrolls or resizes
  // while open - a fixed-position element does not move with the content
  // under it on its own.
  useEffect(() => {
    if (!open) return;
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open, reposition]);

  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  const moveFocus = (nextIndex: number) => {
    const clamped = Math.max(0, Math.min(visibleLanguages.length - 1, nextIndex));
    optionRefs.current[clamped]?.focus();
  };

  const onTriggerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openMenu();
    }
  };

  const onOptionKeyDown = (e: React.KeyboardEvent, index: number) => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        moveFocus(index + 1);
        break;
      case "ArrowUp":
        e.preventDefault();
        moveFocus(index - 1);
        break;
      case "Home":
        e.preventDefault();
        moveFocus(0);
        break;
      case "End":
        e.preventDefault();
        moveFocus(visibleLanguages.length - 1);
        break;
      case "Escape":
        e.preventDefault();
        closeMenu(true);
        break;
      case "Tab":
        // Tabbing out of an open menu should close it rather than leave an
        // invisible listbox capturing focus order.
        closeMenu(false);
        break;
      default:
        break;
    }
  };

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={onTriggerKeyDown}
        className="flex items-center gap-1.5 rounded-full border border-border bg-surface-muted px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary"
      >
        <Globe size={13} />
        {current ? label(current) : i18n.language === "en" ? "English" : i18n.language}
      </button>

      {open &&
        createPortal(
          <>
            <div className="fixed inset-0 z-40" onClick={() => closeMenu()} />
            <div
              role="listbox"
              aria-label={t("languageSwitcher.ariaLabel")}
              style={{ top: coords.top, right: coords.right }}
              className="fixed z-50 flex max-h-[min(24rem,calc(100svh-1rem))] w-72 max-w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-[var(--shadow-card)]"
            >
              <label className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2">
                <Search size={14} className="shrink-0 text-text-muted" />
                <input
                  ref={searchRef}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "ArrowDown" && visibleLanguages.length) {
                      event.preventDefault();
                      optionRefs.current[0]?.focus();
                    } else if (event.key === "Escape") {
                      event.preventDefault();
                      closeMenu(true);
                    }
                  }}
                  placeholder={t("languageSwitcher.search")}
                  className="min-w-0 flex-1 bg-transparent text-sm text-text-primary outline-none placeholder:text-text-muted"
                />
              </label>
              <div className="overflow-y-auto py-1">
              {visibleLanguages.map((lang, i) => (
                <button
                  key={lang.iso}
                  ref={(el) => {
                    optionRefs.current[i] = el;
                  }}
                  type="button"
                  role="option"
                  aria-selected={lang.iso === i18n.language}
                  onClick={() => select(lang.iso)}
                  onKeyDown={(e) => onOptionKeyDown(e, i)}
                  dir="auto"
                  className={`block w-full px-3 py-2 text-start text-sm transition-colors hover:bg-surface-muted focus:bg-surface-muted focus:outline-none ${
                    lang.iso === i18n.language ? "text-accent-primary font-medium" : "text-text-secondary"
                  }`}
                >
                  <bdi dir="auto">{label(lang)}</bdi>
                </button>
              ))}
              {!visibleLanguages.length && <p className="px-3 py-3 text-sm text-text-muted">{t("languageSwitcher.noResults")}</p>}
              </div>
            </div>
          </>,
          document.body,
        )}
    </div>
  );
}
