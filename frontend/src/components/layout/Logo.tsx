/** Abstract circular/spoke motif - restrained nod to a chakra without being literal. */
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="16" cy="16" r="14" stroke="var(--accent-gold)" strokeWidth="1.4" opacity="0.55" />
      <circle cx="16" cy="16" r="8.5" fill="var(--accent-primary)" />
      {Array.from({ length: 8 }).map((_, i) => {
        const angle = (i * Math.PI) / 4;
        const x1 = 16 + Math.cos(angle) * 9.5;
        const y1 = 16 + Math.sin(angle) * 9.5;
        const x2 = 16 + Math.cos(angle) * 13.5;
        const y2 = 16 + Math.sin(angle) * 13.5;
        return (
          <line
            key={i}
            x1={x1}
            y1={y1}
            x2={x2}
            y2={y2}
            stroke="var(--accent-gold)"
            strokeWidth="1.3"
            strokeLinecap="round"
            opacity="0.8"
          />
        );
      })}
      <circle cx="16" cy="16" r="3" fill="var(--color-ink-50)" />
    </svg>
  );
}
