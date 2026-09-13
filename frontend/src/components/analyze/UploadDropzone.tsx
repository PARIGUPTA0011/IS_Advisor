import { useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { FileText, Upload, X } from "lucide-react";

const MAX_BYTES = 25 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".pdf", ".txt"];

interface Props {
  file: File | null;
  onFileSelected: (file: File) => void;
  onClear: () => void;
  error: string | null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadDropzone({ file, onFileSelected, onClear, error }: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const validateAndSelect = (candidate: File) => {
    const ext = candidate.name.slice(candidate.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setLocalError(t("errors.unsupportedFile"));
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setLocalError(t("errors.fileTooLarge"));
      return;
    }
    setLocalError(null);
    onFileSelected(candidate);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) validateAndSelect(dropped);
  };

  const shownError = error ?? localError;

  if (file) {
    return (
      <div className="glass-panel flex items-center justify-between gap-3 rounded-2xl p-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-primary/10 text-accent-primary">
            <FileText size={18} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-text-primary">{file.name}</p>
            <p className="text-xs text-text-muted">{formatSize(file.size)}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClear}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-text-muted transition-colors hover:bg-surface-muted hover:text-text-primary"
          aria-label={t("analyze.removeFile")}
        >
          <X size={16} />
        </button>
      </div>
    );
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
          isDragging ? "border-accent-primary bg-accent-primary/5" : "border-border-strong hover:border-accent-primary/50"
        }`}
      >
        <Upload className="text-accent-primary" size={26} />
        <p className="text-sm font-medium text-text-primary">{t("dashboard.uploadTitle")}</p>
        <p className="text-xs text-text-muted">{t("dashboard.uploadSubtitle")}</p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt"
          className="hidden"
          onChange={(e) => {
            const selected = e.target.files?.[0];
            if (selected) validateAndSelect(selected);
          }}
        />
      </div>
      {shownError && <p className="mt-2 text-xs text-status-withdrawn">{shownError}</p>}
    </div>
  );
}
