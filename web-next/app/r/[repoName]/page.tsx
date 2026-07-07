"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getHistory,
  getResult,
  getSonarHistory,
  startAnalysis,
  type AnalysisResult,
  type HistoryPoint,
  type SonarPoint,
} from "@/lib/api";

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-red-600 text-white",
  high: "bg-orange-500 text-white",
  medium: "bg-yellow-500 text-white",
  low: "bg-green-600 text-white",
};

const CONFIDENCE_BADGE: Record<string, string> = {
  high: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  low: "bg-red-100 text-red-800",
};

const SEVERITY_ORDER = ["critical", "high", "medium", "low"];

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-gray-200 p-5">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}

export default function ResultsPage() {
  const { repoName } = useParams<{ repoName: string }>();
  const router = useRouter();

  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [sonarData, setSonarData] = useState<SonarPoint[] | null>(null);
  const [sonarAvailable, setSonarAvailable] = useState<boolean | null>(null);
  const [debtTab, setDebtTab] = useState<"ai" | "sonar">("ai");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [reanalysing, setReanalysing] = useState(false);
  const [startingHistory, setStartingHistory] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");

  useEffect(() => {
    getResult(repoName)
      .then(setResult)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
    getHistory(repoName).then(setHistory);
    getSonarHistory(repoName).then(({ available, data }) => {
      setSonarAvailable(available);
      setSonarData(data);
    });
  }, [repoName]);

  const categories = useMemo(
    () =>
      result
        ? Array.from(new Set(result.issues.map((i) => i.category))).sort()
        : [],
    [result],
  );

  const filteredIssues = useMemo(() => {
    if (!result) return [];
    return result.issues
      .filter((i) => categoryFilter === "all" || i.category === categoryFilter)
      .filter((i) => severityFilter === "all" || i.severity === severityFilter)
      .slice()
      .sort(
        (a, b) =>
          SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
          b.remediation_minutes - a.remediation_minutes,
      );
  }, [result, categoryFilter, severityFilter]);

  const hotspots = useMemo(() => {
    if (!result?.churn_data) return [];
    const t = result.churn_data.hotspot_threshold;
    return result.churn_data.top_churned_files.filter((f) => f.change_count >= t);
  }, [result]);

  async function handleShare() {
    await navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleReanalyse() {
    if (reanalysing || !result?.repo_url) return;
    setReanalysing(true);
    try {
      const { job_id } = await startAnalysis(result.repo_url, "latest");
      router.push(`/analyse/${job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start re-analysis");
      setReanalysing(false);
    }
  }

  async function handleAnalyseHistory() {
    if (startingHistory || !result?.repo_url) return;
    setStartingHistory(true);
    try {
      const { job_id } = await startAnalysis(result.repo_url, "history");
      router.push(`/analyse/${job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start history analysis");
      setStartingHistory(false);
    }
  }

  if (error) {
    return (
      <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-6">
        <h1 className="text-xl font-semibold">Couldn&apos;t load results</h1>
        <p className="mt-2 text-sm text-gray-500">{error}</p>
        <Link href="/" className="mt-6 text-sm font-semibold text-blue-600 hover:underline">
          ← Back to home
        </Link>
      </main>
    );
  }

  if (!result) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
      </main>
    );
  }

  const chartData = history.map((h) => ({
    date: h.commit_date.slice(0, 10),
    score: h.ai_debt_score,
  }));

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/" className="text-xs font-medium text-gray-400 hover:text-blue-600">
            ← All repositories
          </Link>
          <h1 className="mt-1 text-3xl font-bold">{result.repo_name}</h1>
          <p className="mt-1 text-xs text-gray-500">
            Commit <span className="font-mono">{result.commit.short_hash}</span> ·{" "}
            {result.commit.date.slice(0, 10)} · {result.model}
            {result.duplicates_removed > 0 &&
              ` · ${result.duplicates_removed} duplicate issue${result.duplicates_removed === 1 ? "" : "s"} removed`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleShare}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold transition hover:border-blue-600 hover:text-blue-600"
          >
            {copied ? "Copied!" : "Share"}
          </button>
          <button
            onClick={handleReanalyse}
            disabled={reanalysing || !result.repo_url}
            title={result.repo_url ? undefined : "Original repo URL unknown (analysed before URL tracking)"}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
          >
            {reanalysing ? "Starting…" : "Re-analyse"}
          </button>
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="AI debt score" value={`${result.ai_debt_score.toLocaleString()} min`} />
        <StatCard label="Issues found" value={result.issue_count} />
        <StatCard label="Churn hotspots" value={hotspots.length} />
        <StatCard label="Files scanned" value={result.files_analyzed} />
      </div>

      {result.summary && (
        <div className="mt-6 rounded-xl border border-blue-200 bg-blue-50 p-6">
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">
            AI summary
          </p>
          <p className="mt-2 leading-relaxed text-blue-950">{result.summary}</p>
        </div>
      )}

      <section className="mt-10">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Debt over time</h2>
          <div className="flex rounded-lg border border-gray-200 text-sm font-medium overflow-hidden">
            <button
              onClick={() => setDebtTab("ai")}
              className={`px-4 py-1.5 transition ${debtTab === "ai" ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-800"}`}
            >
              AI Score
            </button>
            <button
              onClick={() => setDebtTab("sonar")}
              className={`px-4 py-1.5 transition border-l border-gray-200 ${debtTab === "sonar" ? "bg-blue-600 text-white" : "text-gray-500 hover:text-gray-800"}`}
            >
              SonarQube SQALE
            </button>
          </div>
        </div>

        {debtTab === "ai" && (
          <>
            {chartData.length >= 2 ? (
              <div className="mt-4 h-64 rounded-xl border border-gray-200 p-4">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#6b7280" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#6b7280" }} />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="score"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="AI debt score (min)"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="mt-4 flex flex-col items-center gap-3 rounded-xl border border-dashed border-gray-300 p-6 text-center">
                <p className="text-sm text-gray-500">
                  Analyse with history mode to see debt over time.
                </p>
                <button
                  onClick={handleAnalyseHistory}
                  disabled={startingHistory || !result.repo_url}
                  title={result.repo_url ? undefined : "Original repo URL unknown (analysed before URL tracking)"}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:opacity-50"
                >
                  {startingHistory ? "Starting…" : "Analyse with history mode"}
                </button>
              </div>
            )}
          </>
        )}

        {debtTab === "sonar" && (
          <>
            {sonarAvailable && sonarData && sonarData.length >= 2 ? (
              <>
                <div className="mt-4 h-64 rounded-xl border border-gray-200 p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={sonarData.map((p) => ({
                        date: p.commit_date.slice(0, 10),
                        sqale: p.sqale_index,
                        failed: p.build_status === "BUILD_FAILED_SCAN_OK",
                      }))}
                      margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#6b7280" }} />
                      <YAxis tick={{ fontSize: 11, fill: "#6b7280" }} />
                      <Tooltip formatter={(v: number) => [`${v.toLocaleString()} min`, "SQALE index"]} />
                      <Line
                        type="monotone"
                        dataKey="sqale"
                        stroke="#059669"
                        strokeWidth={2}
                        dot={{ r: 2 }}
                        name="SQALE index (min)"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-gray-400">
                  SonarQube SQALE data from dissertation pipeline ·{" "}
                  {sonarData.length.toLocaleString()} commits ·{" "}
                  {sonarData.filter((p) => p.build_status === "BUILD_FAILED_SCAN_OK").length} source-only scans
                </p>
              </>
            ) : sonarAvailable === false ? (
              <p className="mt-4 rounded-xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-400">
                SonarQube pipeline data not yet available for this repo.
              </p>
            ) : (
              <div className="mt-4 flex items-center justify-center h-16">
                <span className="h-5 w-5 animate-spin rounded-full border-2 border-green-600 border-t-transparent" />
              </div>
            )}
          </>
        )}
      </section>

      {result.churn_data && result.churn_data.top_churned_files.length > 0 && (
        <section className="mt-10">
          <h2 className="text-lg font-semibold">Churn hotspots</h2>
          <p className="mt-1 text-xs text-gray-500">
            Most frequently changed files across {result.churn_data.total_commits} commits.
            Hotspot threshold: {result.churn_data.hotspot_threshold}+ changes.
          </p>
          <div className="mt-4 overflow-x-auto rounded-xl border border-gray-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
                  <th className="px-4 py-3 font-semibold">File</th>
                  <th className="px-4 py-3 font-semibold">Changes</th>
                  <th className="px-4 py-3 font-semibold">Authors</th>
                </tr>
              </thead>
              <tbody>
                {result.churn_data.top_churned_files.slice(0, 5).map((f) => (
                  <tr key={f.path} className="border-b border-gray-100 last:border-0">
                    <td className="px-4 py-2.5 font-mono text-xs">{f.path}</td>
                    <td className="px-4 py-2.5">{f.change_count}</td>
                    <td className="px-4 py-2.5">{f.author_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="mt-10">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">
            Issues{" "}
            <span className="text-sm font-normal text-gray-400">
              ({filteredIssues.length} of {result.issues.length})
            </span>
          </h2>
          <div className="flex gap-2">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-blue-600"
            >
              <option value="all">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-blue-600"
            >
              <option value="all">All severities</option>
              {SEVERITY_ORDER.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 space-y-4">
          {filteredIssues.map((issue, idx) => (
            <div key={idx} className="rounded-xl border border-gray-200 p-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium capitalize text-gray-700">
                  {issue.category.replace(/_/g, " ")}
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ${SEVERITY_BADGE[issue.severity] ?? "bg-gray-200"}`}
                >
                  {issue.severity}
                </span>
                {issue.confidence && (
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${CONFIDENCE_BADGE[issue.confidence] ?? "bg-gray-100 text-gray-700"}`}
                  >
                    {issue.confidence} confidence
                  </span>
                )}
                <span className="ml-auto text-xs font-semibold text-gray-500">
                  ~{issue.remediation_minutes} min to fix
                </span>
              </div>
              {issue.location && (
                <p className="mt-3 font-mono text-xs text-gray-500">{issue.location}</p>
              )}
              <p className="mt-2 text-sm leading-relaxed">{issue.description}</p>
              {issue.why_debt && (
                <p className="mt-2 text-sm italic leading-relaxed text-gray-600">
                  {issue.why_debt}
                </p>
              )}
              {issue.suggestion && (
                <p className="mt-2 text-sm leading-relaxed text-blue-700">
                  → {issue.suggestion}
                </p>
              )}
            </div>
          ))}
          {filteredIssues.length === 0 && (
            <p className="rounded-xl border border-dashed border-gray-300 p-6 text-sm text-gray-500">
              No issues match the current filters.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
