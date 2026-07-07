"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Code2 } from "lucide-react";
import { getRepos, startAnalysis, type RepoSummary } from "@/lib/api";

function severityStyles(score: number) {
  if (score < 500) {
    return {
      borderAccent: "border-l-green-500",
      iconBg: "bg-green-50",
      iconText: "text-green-600",
      badge: "bg-green-100 text-green-800",
    };
  }
  if (score <= 2000) {
    return {
      borderAccent: "border-l-amber-500",
      iconBg: "bg-amber-50",
      iconText: "text-amber-600",
      badge: "bg-amber-100 text-amber-800",
    };
  }
  return {
    borderAccent: "border-l-red-500",
    iconBg: "bg-red-50",
    iconText: "text-red-600",
    badge: "bg-red-100 text-red-800",
  };
}

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [includeHistory, setIncludeHistory] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [repos, setRepos] = useState<RepoSummary[]>([]);
  const [reposLoaded, setReposLoaded] = useState(false);

  useEffect(() => {
    getRepos()
      .then(setRepos)
      .catch(() => setRepos([]))
      .finally(() => setReposLoaded(true));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim() || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { job_id } = await startAnalysis(url.trim(), includeHistory ? "history" : "latest");
      router.push(`/analyse/${job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-white bg-[radial-gradient(circle,#f3f4f6_1px,transparent_1px)] bg-[length:22px_22px]">
      <nav className="sticky top-0 z-10 border-b border-gray-100 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-6 py-4">
          <span className="font-extrabold tracking-tight text-gray-900">TD Agent</span>
          <a
            href="https://github.com/boluaj16/td-agent"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-gray-500 transition hover:text-blue-600"
          >
            GitHub
          </a>
        </div>
      </nav>

      <main className="mx-auto max-w-2xl px-6 py-20">
        <div className="text-center">
          <div className="mx-auto mb-6 flex w-fit items-center gap-1.5 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-500">
            <span className="text-blue-500">✦</span> Powered by Gemini AI
          </div>

          <h1 className="text-5xl font-extrabold tracking-tight text-gray-900 sm:text-6xl">
            Find technical debt
            <br />
            before it finds{" "}
            <span className="bg-gradient-to-r from-blue-600 to-violet-600 bg-clip-text text-transparent">
              you
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-lg text-lg text-gray-500">
            Paste a GitHub URL. Get an AI debt score, natural language summary,
            and a full issue breakdown.
          </p>
        </div>

        <div className="mx-auto mt-10 w-full max-w-xl rounded-2xl border border-gray-200 bg-white p-2 shadow-sm">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
              className="h-12 flex-1 rounded-xl border-0 bg-transparent px-4 text-sm text-gray-900 outline-none placeholder:text-gray-400 focus:ring-2 focus:ring-blue-100"
            />
            <button
              type="submit"
              disabled={submitting}
              className="h-12 shrink-0 rounded-xl bg-gradient-to-r from-blue-600 to-blue-700 px-6 text-sm font-semibold text-white shadow-sm transition hover:brightness-110 disabled:opacity-50"
            >
              {submitting ? "Starting…" : "Analyse repo"}
            </button>
          </form>
        </div>
        <div className="mx-auto mt-3 flex max-w-xl items-center justify-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-gray-500">
            <input
              type="checkbox"
              checked={includeHistory}
              onChange={(e) => setIncludeHistory(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-100"
            />
            Include commit history (slower)
          </label>
        </div>
        <p className="mx-auto mt-2 max-w-xl text-center text-xs text-gray-400">
          Free · No account required · Public repos only
        </p>
        {error && (
          <p className="mx-auto mt-3 max-w-xl text-center text-sm text-red-600">{error}</p>
        )}

        <section className="mt-20">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-400">
            Recently analysed
          </h2>
          {reposLoaded && repos.length === 0 && (
            <p className="mt-4 text-sm text-gray-500">
              No repositories analysed yet — paste a URL above to get started.
            </p>
          )}
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {repos.map((r) => {
              const sev = severityStyles(r.latest_score);
              return (
                <a
                  key={r.name}
                  href={`/r/${r.name}`}
                  className={`group flex items-start gap-3 rounded-xl border border-gray-200 ${sev.borderAccent} border-l-4 bg-white p-4 transition hover:shadow-sm`}
                >
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${sev.iconBg}`}
                  >
                    <Code2 className={`h-4 w-4 ${sev.iconText}`} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-semibold text-gray-900 group-hover:text-blue-600">
                        {r.name}
                      </span>
                      <span
                        className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-semibold ${sev.badge}`}
                      >
                        {r.latest_score.toLocaleString()}
                        <span className="font-normal opacity-70"> min</span>
                      </span>
                    </div>
                    <p className="mt-1 truncate text-xs text-gray-400">
                      {r.issue_count} issues · last analysed {r.last_analysed}
                    </p>
                  </div>
                </a>
              );
            })}
          </div>
        </section>
      </main>

      <footer className="border-t border-gray-100 py-8 text-center text-xs text-gray-400">
        TD Agent · Built for MSc research at Leeds Beckett University · Powered by Gemini AI
      </footer>
    </div>
  );
}
