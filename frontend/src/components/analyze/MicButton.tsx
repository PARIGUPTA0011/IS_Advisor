import { motion } from "framer-motion";
import { Mic, MicOff, Loader2 } from "lucide-react";
import type { SpeechStatus } from "../../hooks/useSpeechToText";

interface MicButtonProps {
  status: SpeechStatus;
  onToggle: () => void;
  title?: string;
}

/**
 * Compact mic button that sits alongside the textarea's action row.
 *
 * States:
 *   idle        → white/muted mic icon, normal hover
 *   recording   → red pulsing background, MicOff icon ("click to stop")
 *   transcribing→ spinner, disabled
 *   done / error→ idle appearance (parent resets via useSpeechToText.reset)
 */
export function MicButton({ status, onToggle, title }: MicButtonProps) {
  const isRecording = status === "recording";
  const isTranscribing = status === "transcribing";
  const isDisabled = isTranscribing;

  return (
    <motion.button
      type="button"
      aria-label={title ?? (isRecording ? "Stop recording" : "Start recording")}
      title={title ?? (isRecording ? "Stop recording" : "Start voice input")}
      disabled={isDisabled}
      onClick={onToggle}
      whileTap={isDisabled ? undefined : { scale: 0.92 }}
      className={[
        "relative flex h-8 w-8 items-center justify-center rounded-full transition-colors",
        isRecording
          ? "bg-red-500 text-white hover:bg-red-600"
          : isTranscribing
            ? "cursor-not-allowed bg-surface-muted text-text-muted"
            : "bg-surface-muted text-text-secondary hover:bg-accent-primary/15 hover:text-accent-primary",
      ].join(" ")}
    >
      {/* Pulsing ring while recording */}
      {isRecording && (
        <motion.span
          className="absolute inset-0 rounded-full bg-red-500 opacity-60"
          animate={{ scale: [1, 1.55, 1], opacity: [0.6, 0, 0.6] }}
          transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
        />
      )}

      {isTranscribing ? (
        <Loader2 size={16} className="animate-spin" />
      ) : isRecording ? (
        <MicOff size={16} />
      ) : (
        <Mic size={16} />
      )}
    </motion.button>
  );
}
