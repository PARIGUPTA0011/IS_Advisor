import { useTranslation } from "react-i18next";

const TIER_STYLES: Record<string, string> = {
  "Highly relevant": "bg-accent-gold/15 text-accent-gold",
  Related: "bg-accent-primary/10 text-accent-primary",
  "Possibly relevant": "bg-surface-muted text-text-secondary",
};

export function TierBadge({ tier }: { tier: string | null }) {
  const { t } = useTranslation();
  if (!tier) return null;
  const style = TIER_STYLES[tier] ?? "bg-surface-muted text-text-secondary";

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${style}`}>
      {t(`results.tier.${tier}`, tier)}
    </span>
  );
}
