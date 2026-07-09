"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, Check, Loader2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
        <p className="mt-2 text-center text-sm text-muted-foreground">
          This job may have expired (job state is in-memory and cleared on API restart).
        </p>
        <Link href="/" className={cn(buttonVariants({ variant: "outline" }), "mt-6")}>
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

  const progressPct =
    job?.status === "done"
      ? 100
      : Math.round(((activeIdx + (isHistoryAnalysing ? job!.progress.current / job!.progress.total : 0.5)) / STEPS.length) * 100);

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6">
      <div className="bg-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_60%_50%_at_50%_40%,black_10%,transparent_70%)]" />
      <div className="pointer-events-none absolute left-1/2 top-1/3 h-96 w-[48rem] -translate-x-1/2 rounded-full bg-blue-600/15 blur-[110px]" />

      <Card className="relative z-10 w-full max-w-lg p-8">
        <h1 className="text-xl font-semibold">
          Analysing{job?.repo_name ? ` ${job.repo_name}` : ""}…
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          This usually takes a minute or two. You can keep this tab open.
        </p>

        <Progress value={failed ? 0 : progressPct} className="mt-6" />

        <ol className="mt-8 space-y-4">
          {STEPS.map((step, i) => {
            const isDone = i < activeIdx || job?.status === "done";
            const isActive = i === activeIdx && !failed && job?.status !== "done";
            return (
              <li key={step.key} className="flex items-center gap-3">
                <span
                  className={`flex size-6 shrink-0 items-center justify-center rounded-full ${
                    isDone
                      ? "bg-emerald-500/15 text-emerald-400"
                      : isActive
                        ? "bg-blue-500/15 text-blue-400"
                        : "bg-muted text-muted-foreground/40"
                  }`}
                >
                  {isDone ? (
                    <Check className="size-3.5" />
                  ) : isActive ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <span className="size-1.5 rounded-full bg-current" />
                  )}
                </span>
                <span
                  className={
                    isDone
                      ? "text-sm font-medium text-foreground"
                      : isActive
                        ? "text-sm font-medium text-blue-400"
                        : "text-sm text-muted-foreground/50"
                  }
                >
                  {step.key === "analysing" ? analysingLabel : step.label}
                </span>
              </li>
            );
          })}
        </ol>

        {failed && (
          <div className="mt-8 rounded-lg border border-red-500/30 bg-red-500/10 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-red-400">
              <AlertTriangle className="size-4" />
              Analysis failed
            </div>
            <p className="mt-1 whitespace-pre-wrap break-words text-xs text-red-300/80">
              {job?.error ?? "Unknown error"}
            </p>
            <Link
              href="/"
              className={cn(buttonVariants({ variant: "outline", size: "sm" }), "mt-3")}
            >
              Try again →
            </Link>
          </div>
        )}
      </Card>
    </div>
  );
}
