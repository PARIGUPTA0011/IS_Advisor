import { BookOpen, Clock3 } from "lucide-react";

export function EntryPoint({ kind }: { kind: "history" | "library" }) {
  const history = kind === "history";
  return (
    <section className="mx-auto max-w-5xl px-4 py-12 md:px-8">
      <div className="rounded-3xl border border-border bg-bg-elevated p-8 shadow-[var(--shadow-card)]">
        <div className="flex size-12 items-center justify-center rounded-2xl bg-accent-primary/10 text-accent-primary">
          {history ? <Clock3 size={24} /> : <BookOpen size={24} />}
        </div>
        <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-accent-primary">{history ? "Recent analyses" : "Standards library"}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-text-primary">{history ? "Your analysis history" : "Browse Indian Standards"}</h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-text-secondary">{history ? "Your completed procurement analyses will appear here." : "Explore the 35,524-standard corpus and discover connected requirements."}</p>
      </div>
    </section>
  );
}
