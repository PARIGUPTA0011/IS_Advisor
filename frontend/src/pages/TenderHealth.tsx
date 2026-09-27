import { useState } from "react";
import { FileSearch, Upload, AlertTriangle, CheckCircle2 } from "lucide-react";
import { tenderHealth } from "../api/tenderHealth";
import type { TenderHealthReport } from "../api/tenderHealth";

export default function TenderHealth() {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<TenderHealthReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleAnalyze() {
    if (!file) return;

    setLoading(true);
    setError("");
    setReport(null);

    try {
      const result = await tenderHealth(file);
      setReport(result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to analyze tender.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8 md:px-10">
      <div className="mb-8">
        <div className="mb-3 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent-primary/10 text-accent-primary">
            <FileSearch size={22} />
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight">
              Tender Health Check
            </h1>
            <p className="text-sm text-text-secondary">
              Audit cited Indian Standards and identify outdated references.
            </p>
          </div>
        </div>

        <p className="max-w-3xl text-sm leading-6 text-text-secondary">
          Upload a tender to identify cited standards, withdrawn standards,
          replacements, successor parts, and items without standard references.
        </p>
      </div>

      <div className="mb-8 rounded-2xl border border-border bg-bg-elevated p-5 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-border px-4 py-3 transition-colors hover:bg-surface-muted">
            <Upload size={19} className="text-accent-primary" />

            <div>
              <p className="text-sm font-medium text-text-primary">
                {file ? file.name : "Choose a tender"}
              </p>
              <p className="text-xs text-text-muted">
                PDF or TXT
              </p>
            </div>

            <input
              type="file"
              accept=".pdf,.txt"
              className="hidden"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setReport(null);
                setError("");
              }}
            />
          </label>

          <button
            type="button"
            onClick={handleAnalyze}
            disabled={!file || loading}
            className="rounded-xl bg-accent-primary px-5 py-3 text-sm font-semibold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Analyzing..." : "Analyze Tender"}
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
      </div>

      {report && (
        <div className="space-y-8">
                    {report.outdated_standards > 0 ? (
            <div className="rounded-2xl border border-amber-300 bg-amber-50 px-5 py-4">
              <div className="flex items-start gap-3">
                <AlertTriangle
                  size={20}
                  className="mt-0.5 shrink-0 text-amber-700"
                />
                <div>
                  <p className="font-semibold text-amber-900">
                    Action required: {report.outdated_standards} outdated{" "}
                    {report.outdated_standards === 1
                      ? "standard"
                      : "standards"}{" "}
                    found
                  </p>
                  <p className="mt-1 text-sm text-amber-800">
                    Review the replacement or successor parts shown below
                    before using the cited standard.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-green-200 bg-green-50 px-5 py-4">
              <div className="flex items-start gap-3">
                <CheckCircle2
                  size={20}
                  className="mt-0.5 shrink-0 text-green-700"
                />
                <div>
                  <p className="font-semibold text-green-900">
                    No outdated standards found
                  </p>
                  <p className="mt-1 text-sm text-green-800">
                    All cited standards in this tender are currently listed
                    as current.
                  </p>
                </div>
              </div>
            </div>
          )}
          <section>
            <h2 className="mb-4 font-display text-lg font-semibold">
              Report Summary
            </h2>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
              <SummaryCard label="Total items" value={report.total_items} />
              <SummaryCard
                label="With citations"
                value={report.items_with_citations}
              />
              <SummaryCard
                label="Without citations"
                value={report.items_without_citations}
              />
              <SummaryCard
                label="Unique standards"
                value={report.unique_standards_cited}
              />
              <SummaryCard
                label="Current"
                value={report.current_standards}
                icon={<CheckCircle2 size={16} />}
              />
              <SummaryCard
                label="Outdated"
                value={report.outdated_standards}
                icon={<AlertTriangle size={16} />}
              />
            </div>
          </section>

          <section>
            <h2 className="mb-4 font-display text-lg font-semibold">
              Cited Standards
            </h2>

            <div className="space-y-3">
              {report.standards.map((standard) => {
                const outdated = standard.status !== "current";

                return (
                  <div
                    key={standard.cited_as}
                    className={`rounded-2xl border bg-bg-elevated p-5 shadow-sm ${
                      outdated
                        ? "border-amber-300"
                        : "border-border"
                    }`}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <div>
                        <h3 className="font-semibold text-text-primary">
                          {standard.is_number}
                        </h3>
                        <p className="mt-1 text-sm text-text-secondary">
                          {standard.title}
                        </p>
                      </div>

                      <span
                        className={`inline-flex w-fit items-center rounded-full px-3 py-1 text-xs font-semibold ${
                          outdated
                            ? "bg-amber-100 text-amber-800"
                            : "bg-green-100 text-green-800"
                        }`}
                      >
                        {outdated ? "Outdated" : "Current"}
                      </span>
                    </div>

                    {standard.replaced_by_is && (
                      <div className="mt-4 rounded-xl bg-amber-50 px-4 py-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">
                          Replaced by
                        </p>
                        <p className="mt-1 text-sm font-medium text-amber-950">
                          {standard.replaced_by_is}
                        </p>
                      </div>
                    )}

                    {standard.successor_parts.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                          Successor parts
                        </p>
                        <p className="mt-1 text-sm text-text-secondary">
                          {standard.successor_parts.join(", ")}
                        </p>
                      </div>
                    )}

                    {standard.note && (
                      <p className="mt-3 text-xs leading-5 text-text-muted">
                        {standard.note}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          <section>
            <h2 className="mb-4 font-display text-lg font-semibold">
              Items Without Standards
            </h2>

            {report.items_without_standards.length === 0 ? (
              <div className="rounded-2xl border border-border bg-bg-elevated p-5 text-sm text-text-secondary">
                Every parsed item cites a standard.
              </div>
            ) : (
              <div className="rounded-2xl border border-border bg-bg-elevated p-5 shadow-sm">
                <ul className="space-y-2">
                  {report.items_without_standards.map((item, index) => (
                    <li
                      key={index}
                      className="border-b border-border pb-2 text-sm text-text-secondary last:border-0 last:pb-0"
                    >
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border bg-bg-elevated p-4 shadow-sm">
      <div className="flex items-center gap-1.5 text-xs text-text-muted">
        {icon}
        {label}
      </div>
      <p className="mt-2 font-display text-2xl font-semibold text-text-primary">
        {value}
      </p>
    </div>
  );
}