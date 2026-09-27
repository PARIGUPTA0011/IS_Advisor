import { useState } from "react";
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
      setError(err instanceof Error ? err.message : "Failed to analyze tender.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1>Tender Health Check</h1>

      <p>
        Upload a tender to identify cited Indian Standards, outdated standards,
        replacements, and items without standard references.
      </p>

      <input
        type="file"
        accept=".pdf,.txt"
        onChange={(event) => {
          setFile(event.target.files?.[0] ?? null);
          setReport(null);
          setError("");
        }}
      />

      <button
        type="button"
        onClick={handleAnalyze}
        disabled={!file || loading}
      >
        {loading ? "Analyzing..." : "Analyze Tender"}
      </button>

      {error && <p>{error}</p>}

      {report && (
        <div>
          <h2>Report</h2>

          <div>
            <p>Total items: {report.total_items}</p>
            <p>Items with citations: {report.items_with_citations}</p>
            <p>Items without citations: {report.items_without_citations}</p>
            <p>Unique standards cited: {report.unique_standards_cited}</p>
            <p>Current standards: {report.current_standards}</p>
            <p>Outdated standards: {report.outdated_standards}</p>
          </div>

          <h2>Cited Standards</h2>

          {report.standards.length === 0 ? (
            <p>No standards were detected.</p>
          ) : (
            <div>
              {report.standards.map((standard) => (
                <div key={standard.cited_as}>
                  <h3>{standard.is_number}</h3>
                  <p>{standard.title}</p>
                  <p>Status: {standard.status}</p>

                  {standard.replaced_by_is && (
                    <p>Replaced by: {standard.replaced_by_is}</p>
                  )}

                  {standard.successor_parts.length > 0 && (
                    <p>
                      Successor parts:{" "}
                      {standard.successor_parts.join(", ")}
                    </p>
                  )}

                  {standard.note && <p>{standard.note}</p>}
                </div>
              ))}
            </div>
          )}

          <h2>Items Without Standards</h2>

          {report.items_without_standards.length === 0 ? (
            <p>Every parsed item cites a standard.</p>
          ) : (
            <ul>
              {report.items_without_standards.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}