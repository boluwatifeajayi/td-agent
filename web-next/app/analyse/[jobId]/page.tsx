"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getJob, type JobStatus } from "@/lib/api";

const STEPS = [
  { key: "cloning", label: "Cloning repository" },
  { key: "churn", label: "Mapping churn" },
  { key: "selecting", label: "Selecting files" },
  { key: "analysing", label: "Analysing with Gemini" },
  { key: "done", label: "Done" },
] as const;

function stepIndex(stage: string): number {
  const i = STEPS.findIndex((s) => s.key === stage);
  return i === -1 ? 0 : i;
}

function Tick() {
  return (
    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-green-100">
      <svg className="h-3.5 w-3.5 text-green-700" viewBox="0 0 20 20" fill="currentColor">
        <path
          fillRule="evenodd"
          d="M16.7 5.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-4-4a1 1 0 111.4-1.4L8 12.6l7.3-7.3a1 1 0 011.4 0z"
          clipRule="evenodd"
        />
      </svg>
    </span>
  );
}

function Spinner() {
  return (
    <span className="flex h-6 w-6 items-center justify-center">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
    </span>
  );
}

function Dot() {
  return (
    <span className="flex h-6 w-6 items-center justify-center">
      <span className="h-2 w-2 rounded-full bg-gray-300" />
    </span>
  );
}

export default function ProgressPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  const [job, setJob] = useState<JobStatus | null>(null);
  const [notFound, setNotFound] = useState(false);
  const redirected = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const j = await getJob(jobId);
        if (cancelled) return;
        setJob(j);
        if (j.status === "done" && j.result_id && !redirected.current) {
          redirected.current = true;
          router.push(`/r/${j.result_id}`);
        }
      } catch {
        if (!cancelled) setNotFound(true);
      }
    }

    poll();
    const timer = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobId, router]);

  if (notFound) {
    return (
      <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6">
        <h1 className="text-xl font-semibold">Job not found</h1>
        <p className="mt-2 text-sm text-gray-500">
          This job may have expired (job state is in-memory and cleared on API restart).
        </p>
        <Link href="/" className="mt-6 text-sm font-semibold text-blue-600 hover:underline">
          ← Back to home
        </Link>
      </main>
    );
  }

  const stage = job?.progress.stage ?? "queued";
  const activeIdx = job?.status === "done" ? STEPS.length : stepIndex(stage);
  const failed = job?.status === "failed";
  const isHistoryAnalysing =
    job?.mode === "history" && stage === "analysing" && job.progress.total > 1;
  const analysingLabel = isHistoryAnalysing
    ? `Analysing commit ${job.progress.current} of ${job.progress.total}`
    : "Analysing with Gemini";

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold">
        Analysing{job?.repo_name ? ` ${job.repo_name}` : ""}…
      </h1>
      <p className="mt-1 text-sm text-gray-500">
        This usually takes a minute or two. You can keep this tab open.
      </p>

      <ol className="mt-10 space-y-5">
        {STEPS.map((step, i) => {
          const isDone = i < activeIdx || job?.status === "done";
          const isActive = i === activeIdx && !failed && job?.status !== "done";
          return (
            <li key={step.key} className="flex items-center gap-3">
              {isDone ? <Tick /> : isActive ? <Spinner /> : <Dot />}
              <span
                className={
                  isDone
                    ? "text-sm font-medium text-gray-900"
                    : isActive
                      ? "text-sm font-medium text-blue-600"
                      : "text-sm text-gray-400"
                }
              >
                {step.key === "analysing" ? analysingLabel : step.label}
                {isActive &&
                  step.key === "analysing" &&
                  job &&
                  !isHistoryAnalysing &&
                  job.progress.total > 1 && (
                    <span className="ml-2 text-xs text-gray-500">
                      Commit {job.progress.current} of {job.progress.total}
                    </span>
                  )}
              </span>
            </li>
          );
        })}
      </ol>

      {failed && (
        <div className="mt-10 rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-semibold text-red-800">Analysis failed</p>
          <p className="mt-1 whitespace-pre-wrap break-words text-xs text-red-700">
            {job?.error ?? "Unknown error"}
          </p>
          <Link
            href="/"
            className="mt-3 inline-block text-sm font-semibold text-blue-600 hover:underline"
          >
            Try again →
          </Link>
        </div>
      )}
    </main>
  );
}
