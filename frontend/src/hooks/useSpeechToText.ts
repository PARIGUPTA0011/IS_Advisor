import { useCallback, useRef, useState } from "react";
import { transcribeAudio } from "../api/speech";
import type { TranscribeResponse } from "../types/api";

export type SpeechStatus = "idle" | "recording" | "transcribing" | "done" | "error";

interface SpeechState {
  status: SpeechStatus;
  transcript: TranscribeResponse | null;
  error: string | null;
}

interface UseSpeechToTextOptions {
  /** Called with the final transcript text so the parent can fill the query box. */
  onTranscript?: (text: string, transcript: TranscribeResponse) => void;
  /** Force a language for Whisper (omit to let the audio speak for itself). */
  language?: string | null;
}

/**
 * Hook that drives the mic button in Analyze.tsx.
 *
 * Calling `start()` opens the microphone and begins a MediaRecorder session.
 * Calling `stop()` (or `toggle()`) finalises the recording and immediately
 * POSTs it to the /transcribe endpoint – mirroring the "print the transcript
 * before the results" discipline used on the CLI side.  The caller receives the
 * raw TranscribeResponse and, separately, the cleaned-up `text` string through
 * `onTranscript`.
 *
 * `language` is intentionally omitted from the default call so that Whisper
 * detects the spoken language from the audio rather than assuming it matches
 * whatever the UI locale happens to be.
 */
export function useSpeechToText(options: UseSpeechToTextOptions = {}) {
  const { onTranscript, language } = options;

  const [state, setState] = useState<SpeechState>({
    status: "idle",
    transcript: null,
    error: null,
  });

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);

  const start = useCallback(async () => {
    // Reset any previous result before starting a new recording.
    setState({ status: "recording", transcript: null, error: null });
    chunksRef.current = [];

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setState({
        status: "error",
        transcript: null,
        error: "Microphone access was denied. Please allow microphone access and try again.",
      });
      return;
    }

    streamRef.current = stream;

    // Pick a MIME type the backend accepts; fall back gracefully.
    const mimeType = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"]
      .find((t) => MediaRecorder.isTypeSupported(t)) ?? "";

    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      // Stop all mic tracks so the browser removes the recording indicator.
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;

      const blob = new Blob(chunksRef.current, { type: mimeType || "audio/webm" });
      chunksRef.current = [];

      setState((prev) => ({ ...prev, status: "transcribing" }));

      try {
        const result = await transcribeAudio(blob, { language: language ?? undefined });
        setState({ status: "done", transcript: result, error: null });
        onTranscript?.(result.text, result);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Transcription failed. Please try again.";
        setState({ status: "error", transcript: null, error: message });
      }
    };

    recorder.start();
  }, [language, onTranscript]);

  const stop = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  }, []);

  const toggle = useCallback(() => {
    if (state.status === "recording") {
      stop();
    } else {
      void start();
    }
  }, [state.status, start, stop]);

  const reset = useCallback(() => {
    // Belt-and-suspenders: if somehow the stream is still live, kill it.
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setState({ status: "idle", transcript: null, error: null });
  }, []);

  return {
    status: state.status,
    transcript: state.transcript,
    error: state.error,
    isRecording: state.status === "recording",
    isTranscribing: state.status === "transcribing",
    start,
    stop,
    toggle,
    reset,
  };
}
