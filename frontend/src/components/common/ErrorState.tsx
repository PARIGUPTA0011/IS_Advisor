import { AlertTriangle, RotateCcw } from "lucide-react";

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-status-withdrawn/20 bg-status-withdrawn/5 px-6 py-10 text-center">
      <AlertTriangle className="text-status-withdrawn" size={28} />
      <p className="max-w-sm text-sm text-text-secondary">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 flex items-center gap-1.5 rounded-full bg-status-withdrawn/10 px-4 py-1.5 text-sm font-medium text-status-withdrawn transition-colors hover:bg-status-withdrawn/20"
        >
          <RotateCcw size={14} />
          Retry
        </button>
      )}
    </div>
  );
}
