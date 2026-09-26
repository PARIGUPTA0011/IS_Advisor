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

        <div className="mt-4 flex flex-col gap-8">
          <p className="text-sm leading-7 text-text-secondary">{t("settings.aboutBody")}</p>

          <div>
            <h2 className="text-sm font-semibold text-text-primary">{t("about.howItWorks")}</h2>
            <ol className="mt-3 flex flex-col gap-3 text-sm leading-6 text-text-secondary">
              <li><span className="font-medium text-text-primary">1. {t("about.stepOneTitle")}</span> — {t("about.stepOne")}</li>
              <li><span className="font-medium text-text-primary">2. {t("about.stepTwoTitle")}</span> — {t("about.stepTwo")}</li>
              <li><span className="font-medium text-text-primary">3. {t("about.stepThreeTitle")}</span> — {t("about.stepThree")}</li>
            </ol>
          </div>

          <div className="grid grid-cols-2 gap-3 border-y border-border/60 py-5">
            <div>
              <p className="text-lg font-semibold text-text-primary">35,524</p>
              <p className="mt-1 text-xs text-text-secondary">{t("about.standardsIndexed")}</p>
            </div>
            <div>
              <p className="text-lg font-semibold text-text-primary">22</p>
              <p className="mt-1 text-xs text-text-secondary">{t("about.targetLanguages")}</p>
            </div>
          </div>
        </div>

        <p className="mt-8 text-xs text-text-secondary">{t("about.projectLine")}</p>
      </div>
    </section>
  );
}
