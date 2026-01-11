"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./page.module.css";

const PREFETCH_WINDOW = 3;
const BUFFER_POLL_MS = 500;
const STALL_RETRY_LIMIT = 12;
const RESUME_STORAGE_KEY = "pronouncex_reader_resume_v1";

type Segment = {
  segment_id: string;
  index: number;
  status?: string;
  path?: string;
  url?: string;
  url_proxy?: string;
  url_backend?: string;
  error?: string;
  resolved_phonemes?: string | null;
  used_phonemes?: boolean | null;
  resolve_source_counts?: Record<string, number>;
};

type JobManifest = {
  job_id: string;
  status?: string;
  segments: Segment[];
};

type JobResponse = {
  job_id?: string;
  manifest?: JobManifest;
};

type ModelItem = {
  model_id: string;
};

type ModelsResponse = {
  models?: ModelItem[];
};

type DictResponse = {
  key?: string;
  phonemes?: string;
  source_pack?: string;
  target_pack?: string;
  detail?: string;
  error?: string;
};

type DictResult = {
  key: string;
  phonemes?: string;
  source_pack?: string;
  error?: string;
};

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function waitForEvent(
  el: HTMLMediaElement,
  events: string[],
  timeoutMs: number,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    const onEvent = () => {
      cleanup();
      resolve();
    };
    const onTimeout = () => {
      cleanup();
      reject(new Error("Timed out waiting for media"));
    };
    const cleanup = () => {
      events.forEach((event) => el.removeEventListener(event, onEvent));
      if (timeoutId) clearTimeout(timeoutId);
    };

    events.forEach((event) => el.addEventListener(event, onEvent, { once: true }));
    timeoutId = setTimeout(onTimeout, timeoutMs);
  });
}

function segmentUrl(seg: Segment, jobId: string): string | null {
  if (seg.url_proxy) return seg.url_proxy;
  if (seg.url) return seg.url;
  if (seg.segment_id && jobId) {
    return `/api/tts/jobs/${jobId}/segments/${seg.segment_id}`;
  }
  return null;
}

function mergedAudioUrl(jobId: string): string {
  return `/api/tts/jobs/${jobId}/audio.ogg`;
}

async function fetchJob(jobId: string, signal?: AbortSignal): Promise<JobManifest> {
  const res = await fetch(`/api/tts/jobs/${jobId}`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`Job fetch failed: ${res.status}`);
  const data: JobResponse = await res.json();
  const manifest = data.manifest;
  if (!manifest?.job_id) throw new Error("Malformed job manifest");
  if (!manifest.segments?.length) throw new Error("Job has no segments");
  return manifest;
}

async function requestJson(input: RequestInfo, init?: RequestInit): Promise<DictResponse> {
  const res = await fetch(input, { cache: "no-store", ...init });
  const data = (await res.json().catch(() => ({}))) as DictResponse;
  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : `Request failed: ${res.status}`;
    throw new Error(detail);
  }
  return data;
}

async function fetchModels(signal?: AbortSignal): Promise<ModelItem[]> {
  const res = await fetch("/api/models", { cache: "no-store", signal });
  if (!res.ok) throw new Error(`Models fetch failed: ${res.status}`);
  const data = (await res.json().catch(() => ({}))) as ModelsResponse;
  return data.models ?? [];
}

export default function Home() {
  const [text, setText] = useState(
    "Gojo greets his senpai, then walks across the city. This line should be followed by more sentences.",
  );
  const [status, setStatus] = useState<string>("");
  const [isBusy, setIsBusy] = useState(false);

  const [jobId, setJobId] = useState<string>("");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [currentIndex, setCurrentIndex] = useState<number>(-1);
  const [currentSrc, setCurrentSrc] = useState<string | null>(null);
  const [needsResume, setNeedsResume] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [unlocked, setUnlocked] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [fallbackActive, setFallbackActive] = useState(false);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [modelsLoading, setModelsLoading] = useState(true);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>("");

  const [dictKey, setDictKey] = useState("Gojo Satoru");
  const [dictPhonemes, setDictPhonemes] = useState("");
  const [dictResult, setDictResult] = useState<DictResult | null>(null);
  const [dictBusy, setDictBusy] = useState(false);
  const [promoteKey, setPromoteKey] = useState("");
  const [promoteStatus, setPromoteStatus] = useState("");
  const [promoteBusy, setPromoteBusy] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const segmentsRef = useRef<Segment[]>([]);
  const jobIdRef = useRef(jobId);
  const playSeqRef = useRef(0);
  const playRetryRef = useRef<Record<number, number>>({});
  const stallRetryRef = useRef<Record<number, number>>({});
  const prefetchRef = useRef<Set<string>>(new Set());
  const resumeRef = useRef<{ index: number; offset: number } | null>(null);
  const lastResumeWriteRef = useRef(0);

  const readyCount = useMemo(
    () => segments.filter((s) => s.status === "ready" || Boolean(s.path)).length,
    [segments],
  );
  const errorCount = useMemo(
    () => segments.filter((s) => s.status === "error").length,
    [segments],
  );
  const totalCount = segments.length || 0;
  const currentSegment = currentIndex >= 0 ? segments[currentIndex] : null;
  const firstSegment = segments.length > 0 ? segments[0] : null;
  const resolvedLabel =
    currentSegment && "resolved_phonemes" in currentSegment
      ? currentSegment.resolved_phonemes
        ? "yes"
        : "no"
      : "—";
  const usedLabel =
    currentSegment && "used_phonemes" in currentSegment
      ? currentSegment.used_phonemes === null || currentSegment.used_phonemes === undefined
        ? "—"
        : currentSegment.used_phonemes
          ? "true"
          : "false"
      : "—";

  useEffect(() => {
    segmentsRef.current = segments;
  }, [segments]);

  useEffect(() => {
    jobIdRef.current = jobId;
  }, [jobId]);

  useEffect(() => {
    const abort = new AbortController();
    setModelsLoading(true);
    setModelsError(null);
    fetchModels(abort.signal)
      .then((items) => {
        setModels(items);
        setSelectedModel((current) => {
          if (current && items.some((m) => m.model_id === current)) return current;
          return items[0]?.model_id ?? "";
        });
        setModelsLoading(false);
      })
      .catch((error) => {
        if (abort.signal.aborted) return;
        const message = error instanceof Error ? error.message : "Failed to load models";
        setModelsError(message);
        setModelsLoading(false);
      });
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (jobIdRef.current) return;
    let parsed: { job_id: string; segment_index: number; time_offset: number } | null =
      null;
    try {
      const raw = localStorage.getItem(RESUME_STORAGE_KEY);
      if (raw) parsed = JSON.parse(raw);
    } catch (error) {
      console.warn("resume token parse failed", error);
    }
    if (!parsed?.job_id) return;
    const resumeJobId = parsed.job_id;
    const resumeIndex = Number(parsed.segment_index || 0);
    const resumeOffset = Number(parsed.time_offset || 0);
    if (!resumeJobId) return;

    abortRef.current?.abort();
    abortRef.current = new AbortController();
    resumeRef.current = { index: resumeIndex, offset: Math.max(resumeOffset, 0) };
    setIsBusy(true);
    setStatus("Restored previous session. Tap Resume to continue.");
    setNeedsResume(true);
    setUnlocked(false);

    fetchJob(resumeJobId, abortRef.current.signal)
      .then((manifest) => {
        const sorted = [...manifest.segments].sort(
          (a, b) => (a.index ?? 0) - (b.index ?? 0),
        );
        setJobId(resumeJobId);
        setSegments(sorted);
        setCurrentIndex(Math.min(resumeIndex, Math.max(sorted.length - 1, 0)));
        pollJob(resumeJobId, abortRef.current!.signal).catch((error) => {
          if (abortRef.current?.signal.aborted) return;
          const message = error instanceof Error ? error.message : "Unknown error";
          setStatus(message);
          setIsBusy(false);
        });
      })
      .catch((error) => {
        const message = error instanceof Error ? error.message : "Failed to restore session";
        setStatus(message);
        setIsBusy(false);
        clearResumeToken();
      });
  }, []);

  const stopAudio = () => {
    const player = audioRef.current;
    if (player) {
      player.pause();
      player.currentTime = 0;
    }
    setCurrentSrc(null);
    setNeedsResume(false);
    setIsPlaying(false);
  };

  const clearResumeToken = () => {
    try {
      localStorage.removeItem(RESUME_STORAGE_KEY);
    } catch (error) {
      console.warn("resume token clear failed", error);
    }
  };

  const writeResumeToken = (index: number, offset: number) => {
    const currentJobId = jobIdRef.current;
    if (!currentJobId || fallbackActive) return;
    try {
      const payload = {
        job_id: currentJobId,
        segment_index: index,
        time_offset: offset,
        updated_at: Date.now(),
      };
      localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(payload));
    } catch (error) {
      console.warn("resume token write failed", error);
    }
  };

  const cancel = async () => {
    const currentJobId = jobIdRef.current;
    if (currentJobId) {
      fetch(`/api/tts/jobs/${currentJobId}/cancel`, { method: "POST" }).catch(
        () => undefined,
      );
    }
    abortRef.current?.abort();
    abortRef.current = null;
    stopAudio();
    clearResumeToken();
    setIsBusy(false);
    setStatus("Canceled.");
    setJobId("");
    setSegments([]);
    setCurrentIndex(-1);
    setNeedsResume(false);
    setUnlocked(false);
    setFallbackActive(false);
    setIsBuffering(false);
  };

  const stopPlayback = () => {
    abortRef.current?.abort();
    stopAudio();
    setStatus("Stopped.");
    setIsBusy(false);
    setNeedsResume(false);
    setIsBuffering(false);
    setFallbackActive(false);
  };

  const sourceCountsLabel = (segment: Segment | null) => {
    if (!segment?.resolve_source_counts) return "—";
    const entries = Object.entries(segment.resolve_source_counts);
    if (!entries.length) return "—";
    return entries.map(([key, value]) => `${key}:${value}`).join(", ");
  };

  const pollJob = async (jobIdValue: string, signal: AbortSignal) => {
    for (let i = 0; i < 600; i += 1) {
      if (signal.aborted) throw new Error("Request canceled");

      const manifest = await fetchJob(jobIdValue, signal);
      const sorted = [...manifest.segments].sort(
        (a, b) => (a.index ?? 0) - (b.index ?? 0),
      );
      setSegments(sorted);

      const jobStatus = manifest.status || "";
      if (jobStatus === "canceled") {
        setIsBusy(false);
        setStatus("Canceled.");
        return;
      }
      const allReady = sorted.every(
        (s) => s.status === "ready" || s.status === "error" || Boolean(s.path),
      );
      if (jobStatus.startsWith("complete") || allReady) {
        setIsBusy(false);
        setIsBuffering(false);
        return;
      }

      await sleep(500);
    }
    throw new Error("Timed out waiting for synthesis");
  };

  const prefetchSegment = async (index: number, jobIdValue: string) => {
    const seg = segmentsRef.current[index];
    if (!seg) return;
    const url = segmentUrl(seg, jobIdValue);
    if (!url) return;
    const key = `${jobIdValue}:${seg.segment_id || index}`;
    if (prefetchRef.current.has(key)) return;
    prefetchRef.current.add(key);
    try {
      const head = await fetch(url, { method: "HEAD", cache: "no-store" });
      if (!head.ok) return;
      await fetch(url, { method: "GET", cache: "force-cache" });
    } catch {
      // Prefetch is best-effort.
    }
  };

  const prefetchWindow = (index: number, jobIdValue: string) => {
    for (let offset = 1; offset <= PREFETCH_WINDOW; offset += 1) {
      void prefetchSegment(index + offset, jobIdValue);
    }
  };

  const handleSynthesize = async (overrideText?: string) => {
    const payloadText = overrideText ?? text;
    if (!payloadText.trim()) {
      setStatus("Enter some text first.");
      return;
    }

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    stopAudio();
    clearResumeToken();
    setIsBusy(true);
    setStatus("Submitting job...");
    setJobId("");
    setSegments([]);
    setCurrentIndex(-1);
    setNeedsResume(false);
    setUnlocked(false);
    setFallbackActive(false);
    setIsBuffering(false);
    playRetryRef.current = {};
    stallRetryRef.current = {};
    prefetchRef.current.clear();

    try {
      const res = await fetch("/api/tts/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: payloadText,
          prefer_phonemes: true,
          model_id: selectedModel || undefined,
        }),
        signal: abortRef.current.signal,
      });
      if (!res.ok) throw new Error(`Submit failed: ${res.status}`);

      const data: JobResponse = await res.json();
      const newJobId = data.job_id;
      const manifest = data.manifest;

      if (!newJobId || !manifest?.segments?.length) throw new Error("No segments returned");

      const sorted = [...manifest.segments].sort(
        (a, b) => (a.index ?? 0) - (b.index ?? 0),
      );
      setJobId(newJobId);
      setSegments(sorted);
      setCurrentIndex(0);
      setStatus("Synthesizing…");

      // Start polling in the background.
      pollJob(newJobId, abortRef.current.signal).catch((error) => {
        if (abortRef.current?.signal.aborted) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setStatus(message);
        setIsBusy(false);
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setStatus(message);
      setIsBusy(false);
    }
  };

  const handleTestSequential = () => {
    const sample =
      "Gojo greets his senpai, then walks across the city. This line should be followed by more sentences. " +
      "Add another sentence so chunking happens. This is a long sample for sequential playback testing.";
    console.log("TEST SEQUENTIAL START");
    setText(sample);
    void handleSynthesize(sample);
  };

  const playMergedFallback = async (reason: string) => {
    const currentJobId = jobIdRef.current;
    if (!currentJobId || fallbackActive) return;
    const player = audioRef.current;
    if (!player) return;

    playSeqRef.current += 1;
    setFallbackActive(true);
    setIsBuffering(false);
    setStatus(reason);
    clearResumeToken();
    const url = mergedAudioUrl(currentJobId);
    setCurrentSrc(url);
    player.pause();
    player.src = url;
    player.load();

    try {
      await waitForEvent(player, ["canplay", "loadeddata"], 5000);
    } catch (error) {
      console.warn("merge fallback wait failed", error);
    }

    try {
      await player.play();
      setNeedsResume(false);
      setIsPlaying(true);
      setUnlocked(true);
      setIsBuffering(false);
    } catch (error) {
      const err = error as Error | undefined;
      console.warn("merge fallback play failed", err?.name, err?.message);
      setNeedsResume(true);
      setIsPlaying(false);
    }
  };

  const waitForSegmentReady = async (index: number) => {
    setIsBuffering(true);
    setStatus(`Buffering segment ${index + 1}...`);
    for (let i = 0; i < 600; i += 1) {
      if (abortRef.current?.signal.aborted) return null;
      const seg = segmentsRef.current[index];
      if (!seg) return null;
      if (seg.status === "error" || seg.status === "ready" || seg.path) {
        stallRetryRef.current[index] = 0;
        setIsBuffering(false);
        return seg;
      }
      const retries = (stallRetryRef.current[index] || 0) + 1;
      stallRetryRef.current[index] = retries;
      if (retries >= STALL_RETRY_LIMIT) {
        await playMergedFallback("Buffering too long. Switching to merged audio...");
        setIsBuffering(false);
        return null;
      }
      await sleep(BUFFER_POLL_MS);
    }
    setIsBuffering(false);
    return segmentsRef.current[index] ?? null;
  };

  const playSegment = async (index: number, url: string) => {
    const player = audioRef.current;
    if (!player) return;

    player.pause();
    player.src = url;
    player.load();

    try {
      await waitForEvent(player, ["canplay", "loadeddata"], 5000);
    } catch (error) {
      console.warn("play() wait failed", error);
    }

    const resume = resumeRef.current;
    if (resume && resume.index === index && resume.offset > 0) {
      player.currentTime = resume.offset;
      resumeRef.current = null;
    }

    try {
      await player.play();
      setNeedsResume(false);
      setIsPlaying(true);
      setUnlocked(true);
      setIsBuffering(false);
    } catch (error) {
      const err = error as Error | undefined;
      console.warn("play() failed", err?.name, err?.message);
      if (err?.name === "NotAllowedError") {
        setStatus("Tap Resume to continue");
        setNeedsResume(true);
        setIsPlaying(false);
        setUnlocked(false);
      } else {
        const tries = playRetryRef.current[index] || 0;
        if (tries < 1) {
          playRetryRef.current[index] = tries + 1;
          await playSegment(index, url);
          return;
        }
        setStatus(`Skipping segment ${index + 1} (playback error)`);
        setIsPlaying(false);
        setCurrentIndex(index + 1);
      }
    }
  };

  const startSegment = async (index: number) => {
    if (index < 0) return;
    const currentJobId = jobIdRef.current;
    if (!currentJobId) return;
    if (fallbackActive) return;

    const seq = (playSeqRef.current += 1);
    if (index >= segmentsRef.current.length) {
      setStatus("Finished.");
      clearResumeToken();
      return;
    }
    let seg = segmentsRef.current[index];
    if (!seg) return;

    if (seg.status === "error") {
      setStatus(`Skipping segment ${index + 1} (error: ${seg.error || "unknown"})`);
      if (index + 1 < segmentsRef.current.length) {
        setCurrentIndex(index + 1);
      } else {
        setStatus("Finished.");
      }
      return;
    }

    if (!(seg.status === "ready" || seg.path)) {
      seg = await waitForSegmentReady(index);
    }

    if (seq !== playSeqRef.current) return;
    if (!seg) return;
    if (seg.status === "error") {
      setStatus(`Skipping segment ${index + 1} (error: ${seg.error || "unknown"})`);
      if (index + 1 < segmentsRef.current.length) {
        setCurrentIndex(index + 1);
      } else {
        setStatus("Finished.");
      }
      return;
    }

    const url = segmentUrl(seg, currentJobId);
    if (!url) {
      setStatus(`No URL for segment ${index + 1}`);
      return;
    }

    console.log("PLAY", index + 1, url);
    setCurrentSrc(url);
    setStatus(`Playing segment ${index + 1}/${totalCount || 1}`);
    prefetchWindow(index, currentJobId);
    await playSegment(index, url);
  };

  useEffect(() => {
    if (currentIndex < 0) return;
    void startSegment(currentIndex);
  }, [currentIndex]);

  useEffect(() => {
    const player = audioRef.current;
    if (!player) return;

    const onTimeUpdate = () => {
      if (fallbackActive) return;
      if (currentIndex < 0) return;
      const now = Date.now();
      if (now - lastResumeWriteRef.current < 2000) return;
      lastResumeWriteRef.current = now;
      writeResumeToken(currentIndex, player.currentTime || 0);
    };

    player.addEventListener("timeupdate", onTimeUpdate);
    return () => {
      player.removeEventListener("timeupdate", onTimeUpdate);
    };
  }, [currentIndex, fallbackActive]);

  const handleEnded = () => {
    if (fallbackActive) {
      stopAudio();
      setStatus("Finished.");
      setFallbackActive(false);
      clearResumeToken();
      return;
    }
    if (currentIndex < 0) return;
    console.log("ENDED", currentIndex + 1);
    stopAudio();

    const nextIndex = currentIndex + 1;
    if (nextIndex >= segments.length) {
      setStatus("Finished.");
      clearResumeToken();
      return;
    }

    setCurrentIndex(nextIndex);
    const nextSeg = segmentsRef.current[nextIndex];
    if (!(nextSeg?.status === "ready" || nextSeg?.path)) {
      setStatus(`Waiting for segment ${nextIndex + 1}...`);
      setIsBuffering(true);
    }
  };

  const handlePlaybackError = () => {
    if (fallbackActive) return;
    if (currentIndex < 0) return;
    const tries = playRetryRef.current[currentIndex] || 0;
    const seg = segmentsRef.current[currentIndex];
    const currentJobId = jobIdRef.current;
    if (!seg || !currentJobId) return;
    const url = segmentUrl(seg, currentJobId);
    if (!url) return;

    if (tries < 1) {
      playRetryRef.current[currentIndex] = tries + 1;
      void playSegment(currentIndex, url);
      return;
    }
    setStatus(`Skipping segment ${currentIndex + 1} (playback error)`);
    setCurrentIndex(currentIndex + 1);
  };

  const handleResume = async () => {
    const player = audioRef.current;
    if (!player) return;
    try {
      await player.play();
      setNeedsResume(false);
      setIsPlaying(true);
      setUnlocked(true);
    } catch (error) {
      const err = error as Error | undefined;
      console.warn("play() failed", err?.name, err?.message);
      setStatus("Tap Resume to continue");
      setNeedsResume(true);
    }
  };

  const handleDictLookup = async () => {
    const key = dictKey.trim();
    if (!key) {
      setDictResult({ key: "", error: "Enter a key to lookup." });
      return;
    }
    setDictBusy(true);
    try {
      const data = await requestJson(
        `/api/dicts/lookup?key=${encodeURIComponent(key)}`,
      );
      setDictResult({
        key: data.key ?? key,
        phonemes: data.phonemes,
        source_pack: data.source_pack,
      });
      setPromoteKey(data.key ?? key);
      if (data.phonemes) {
        setDictPhonemes(data.phonemes);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setDictResult({ key, error: message });
    } finally {
      setDictBusy(false);
    }
  };

  const handleDictLearn = async () => {
    const key = dictKey.trim();
    if (!key) {
      setDictResult({ key: "", error: "Enter a key to learn." });
      return;
    }
    setDictBusy(true);
    try {
      const data = await requestJson("/api/dicts/learn", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      setDictResult({
        key: data.key ?? key,
        phonemes: data.phonemes,
        source_pack: data.source_pack,
      });
      setPromoteKey(data.key ?? key);
      if (data.phonemes) {
        setDictPhonemes(data.phonemes);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setDictResult({ key, error: message });
    } finally {
      setDictBusy(false);
    }
  };

  const handleDictOverride = async () => {
    const key = dictKey.trim();
    const phonemes = dictPhonemes.trim();
    if (!key) {
      setDictResult({ key: "", error: "Enter a key to override." });
      return;
    }
    if (!phonemes) {
      setDictResult({ key, error: "Enter phonemes to override." });
      return;
    }
    setDictBusy(true);
    try {
      await requestJson("/api/dicts/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pack: "local_overrides", key, phonemes }),
      });
      setDictResult({
        key,
        phonemes,
        source_pack: "local_overrides",
      });
      setPromoteKey(key);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setDictResult({ key, error: message });
    } finally {
      setDictBusy(false);
    }
  };

  const handlePromote = async () => {
    const key = promoteKey.trim();
    if (!key) {
      setPromoteStatus("Enter a key to promote.");
      return;
    }
    setPromoteBusy(true);
    setPromoteStatus("");
    try {
      const data = await requestJson("/api/dicts/promote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, target_pack: "local_overrides", overwrite: false }),
      });
      setPromoteStatus(
        `Promoted ${data.key ?? key} to ${data.target_pack ?? "local_overrides"}.`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setPromoteStatus(message);
    } finally {
      setPromoteBusy(false);
    }
  };

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <div className={styles.header}>
          <div>
            <p className={styles.eyebrow}>PronounceX</p>
            <h1 className={styles.title}>TTS Job Runner</h1>
          </div>
          <p className={styles.subtitle}>
            Same-origin proxy to the FastAPI TTS backend. Submit text, then listen segment by segment.
          </p>
        </div>

        <div className={styles.panel}>
          <label className={styles.label} htmlFor="tts-model">
            Model
          </label>
          <select
            id="tts-model"
            className={styles.textInput}
            value={selectedModel}
            onChange={(event) => setSelectedModel(event.target.value)}
            disabled={modelsLoading || !models.length}
          >
            {models.map((model) => (
              <option key={model.model_id} value={model.model_id}>
                {model.model_id}
              </option>
            ))}
          </select>
          {modelsLoading ? (
            <p className={styles.helperText}>Loading models…</p>
          ) : null}
          {modelsError ? <p className={styles.errorText}>{modelsError}</p> : null}
          <label className={styles.label} htmlFor="tts-text">
            Text
          </label>
          <textarea
            id="tts-text"
            className={styles.textarea}
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={6}
            placeholder="Paste a paragraph to synthesize."
          />
          <div className={styles.controls}>
            <button className={styles.button} onClick={handleSynthesize}>
              {isBusy ? "Restart" : "Synthesize"}
            </button>
            <button className={styles.button} onClick={cancel} disabled={!isBusy && !jobId}>
              Cancel
            </button>
            <span className={styles.status}>
              {status}{" "}
              {isBuffering ? <span>(buffering)</span> : null}{" "}
              {totalCount > 0 ? (
                <span>
                  ({readyCount}/{totalCount} ready)
                </span>
              ) : null}
            </span>
          </div>
        </div>

        <div className={styles.panel}>
          <div className={styles.headerRow}>
            <div>
              <p className={styles.eyebrow}>Dictionary Tools</p>
              <p className={styles.helperText}>
                Lookup, learn, and override pronunciations via the same-origin API.
              </p>
            </div>
          </div>
          <label className={styles.label} htmlFor="dict-key">
            Key
          </label>
          <input
            id="dict-key"
            className={styles.textInput}
            value={dictKey}
            onChange={(event) => setDictKey(event.target.value)}
            placeholder="Word or phrase"
          />
          <div className={styles.controls}>
            <button className={styles.button} onClick={handleDictLookup} disabled={dictBusy}>
              Lookup
            </button>
            <button className={styles.button} onClick={handleDictLearn} disabled={dictBusy}>
              Learn
            </button>
          </div>
          <label className={styles.label} htmlFor="dict-phonemes">
            Phonemes
          </label>
          <textarea
            id="dict-phonemes"
            className={styles.textareaSmall}
            value={dictPhonemes}
            onChange={(event) => setDictPhonemes(event.target.value)}
            rows={3}
            placeholder="Paste or edit phonemes for override"
          />
          <div className={styles.controls}>
            <button className={styles.button} onClick={handleDictOverride} disabled={dictBusy}>
              Override
            </button>
          </div>
          {dictResult ? (
            <div className={styles.resultBox}>
              <span>Key: {dictResult.key || dictKey || "—"}</span>
              <span>Source pack: {dictResult.source_pack || "—"}</span>
              <span>Phonemes: {dictResult.phonemes || "—"}</span>
              {dictResult.error ? (
                <span className={styles.errorText}>Error: {dictResult.error}</span>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className={styles.player}>
          <audio
            ref={audioRef}
            controls
            playsInline
            preload="auto"
            onEnded={handleEnded}
            onError={handlePlaybackError}
            onStalled={handlePlaybackError}
          />
          {currentSrc ? null : <div className={styles.emptyPlayer}>Audio will appear here.</div>}
          <div className={styles.meta}>
            <span>Job: {jobId || "—"}</span>
            <span>
              Segment: {currentIndex >= 0 ? currentIndex + 1 : 0}/{totalCount || 1}
            </span>
            <span>Errors: {errorCount}</span>
            <span>Resolved phonemes: {resolvedLabel}</span>
            <span>Used phonemes: {usedLabel}</span>
            <span>Sources: {sourceCountsLabel(currentSegment)}</span>
          </div>
          <div className={styles.controls}>
            <button className={styles.button} onClick={stopPlayback} disabled={!jobId}>
              Stop
            </button>
            <button className={styles.button} onClick={handleTestSequential} disabled={isBusy}>
              Test Sequential
            </button>
          </div>
          {segments.length > 0 ? (
            <div className={styles.controls}>
              <input
                className={styles.textInput}
                value={promoteKey}
                onChange={(event) => setPromoteKey(event.target.value)}
                placeholder="Key to promote"
              />
              <button
                className={styles.button}
                onClick={handlePromote}
                disabled={promoteBusy}
              >
                Promote
              </button>
              {promoteStatus ? <span className={styles.status}>{promoteStatus}</span> : null}
              {firstSegment?.resolved_phonemes ? (
                <span className={styles.helperText}>
                  Segment 1 phonemes: {firstSegment.resolved_phonemes}
                </span>
              ) : null}
              {firstSegment?.resolve_source_counts ? (
                <span className={styles.helperText}>
                  Segment 1 sources: {sourceCountsLabel(firstSegment)}
                </span>
              ) : null}
            </div>
          ) : null}
          {needsResume ? (
            <div className={styles.controls}>
              <button className={styles.button} onClick={handleResume}>
                Resume
              </button>
            </div>
          ) : null}

          {segments.length > 0 ? (
            <div className={styles.segmentList}>
              {segments.map((s, idx) => (
                <div key={s.segment_id} className={styles.segmentRow}>
                  <span>
                    {idx + 1}. {s.status || "queued"}
                  </span>
                  {s.status === "error" ? <span>{s.error}</span> : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
