import { Info } from "lucide-react";
import { useTranslation } from "react-i18next";

export function About() {
  const { t } = useTranslation();

  return (
    <section className="mx-auto max-w-2xl px-4 py-10 md:px-8">
      <div className="glass-panel rounded-2xl p-6 md:p-8">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-accent-primary/10 text-accent-primary">
          <Info size={24} />
        </div>
        <h1 className="mt-6 font-display text-3xl font-semibold text-text-primary">{t("settings.about")}</h1>
        <p className="mt-4 text-sm leading-7 text-text-secondary">{t("settings.aboutBody")}</p>
      </div>
    </section>
  );
}
