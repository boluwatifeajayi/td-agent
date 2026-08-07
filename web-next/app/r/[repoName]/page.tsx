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
  ArrowLeft,
  BadgeCheck,
  Bug,
  Check,
  FileCode2,
  Flame,
  GitCommitHorizontal,
  RotateCw,
  Share2,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StatCard } from "@/components/dashboard/stat-card";
import { ModelBadge } from "@/components/dashboard/model-badge";
import { ProviderComparison } from "@/components/dashboard/provider-comparison";
import { GroupedIssues } from "@/components/dashboard/grouped-issues";
import { cn } from "@/lib/utils";
import { confidenceLabel } from "@/lib/confidence";
import {
  getHistory,
  getResult,
  getSonarHistory,
  startAnalysis,
  type AnalysisResult,
  type HistoryPoint,
  type SonarPoint,
} from "@/lib/api";

const SEVERITY_ORDER = ["critical", "high", "medium", "low"];
const CHART_GRID = "oklch(1 0 0 / 8%)";
const CHART_TICK = "oklch(0.708 0 0)";

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
        <p className="mt-2 text-center text-sm text-muted-foreground">{error}</p>
        <Link href="/" className={cn(buttonVariants({ variant: "outline" }), "mt-6")}>
          ← Back to home
        </Link>
      </main>
    );
  }

  if (!result) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <span className="size-6 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
      </main>
    );
  }

  const chartData = history.map((h) => ({
    date: h.commit_date.slice(0, 10),
    score: h.ai_debt_score,
  }));

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-60 [mask-image:radial-gradient(ellipse_80%_40%_at_50%_0%,black_5%,transparent_60%)]" />

      <main className="relative z-10 mx-auto max-w-5xl px-6 py-12 pt-20 lg:pt-12">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link
              href="/"
              className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="size-3" />
              All repositories
            </Link>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">{result.repo_name}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
              <span className="font-mono">{result.commit.short_hash}</span>
              <span>·</span>
              <span>{result.commit.date.slice(0, 10)}</span>
              <span>·</span>
              <ModelBadge model={result.model} provider={result.provider} className="h-4 px-1.5 text-[10px]" />
              {result.duplicates_removed > 0 && (
                <>
                  <span>·</span>
                  <span>
                    {result.duplicates_removed} duplicate issue
                    {result.duplicates_removed === 1 ? "" : "s"} removed
                  </span>
                </>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleShare} className="gap-1.5">
              {copied ? <Check className="size-3.5" /> : <Share2 className="size-3.5" />}
              {copied ? "Copied!" : "Share"}
            </Button>
            <Button
              size="sm"
              onClick={handleReanalyse}
              disabled={reanalysing || !result.repo_url}
              title={result.repo_url ? undefined : "Original repo URL unknown (analysed before URL tracking)"}
              className="gap-1.5"
            >
              <RotateCw className="size-3.5" />
              {reanalysing ? "Starting…" : "Re-analyse"}
            </Button>
          </div>
        </div>

        <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatCard
            label="AI debt score"
            value={`${result.ai_debt_score.toLocaleString()} min`}
            icon={Flame}
            badge={<ModelBadge model={result.model} provider={result.provider} className="h-4 px-1.5 text-[10px]" />}
          />
          <StatCard label="Issues found" value={result.issue_count} icon={Bug} />
          <StatCard
            label="Avg. confidence"
            value={confidenceLabel(result.avg_confidence)}
            icon={BadgeCheck}
            hint={result.avg_confidence !== null ? `${result.avg_confidence.toFixed(1)} / 3` : undefined}
          />
          <StatCard label="Churn hotspots" value={hotspots.length} icon={GitCommitHorizontal} />
          <StatCard label="Files scanned" value={result.files_analyzed} icon={FileCode2} />
        </div>

        {result.summary && (
          <Card className="mt-6 border-blue-500/20 bg-blue-500/[0.06] p-6">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-400">
              AI summary
            </p>
            <p className="mt-2 leading-relaxed text-foreground/90">{result.summary}</p>
          </Card>
        )}

        {result.comparison && <ProviderComparison comparison={result.comparison} />}

        <section className="mt-10">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Debt over time</h2>
            <div className="flex rounded-lg border border-border p-0.5 text-sm font-medium">
              <button
                onClick={() => setDebtTab("ai")}
                className={cn(
                  "rounded-md px-3 py-1 transition",
                  debtTab === "ai"
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                AI Score
              </button>
              <button
                onClick={() => setDebtTab("sonar")}
                className={cn(
                  "rounded-md px-3 py-1 transition",
                  debtTab === "sonar"
                    ? "bg-secondary text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                SonarQube SQALE
              </button>
            </div>
          </div>

          {debtTab === "ai" && (
            <>
              {chartData.length >= 2 ? (
                <Card className="mt-4 h-64 p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                      <XAxis dataKey="date" tick={{ fontSize: 11, fill: CHART_TICK }} />
                      <YAxis tick={{ fontSize: 11, fill: CHART_TICK }} />
                      <Tooltip
                        contentStyle={{
                          background: "oklch(0.12 0 0)",
                          border: "1px solid oklch(1 0 0 / 12%)",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                        labelStyle={{ color: "oklch(0.708 0 0)" }}
                      />
                      <Line
                        type="monotone"
                        dataKey="score"
                        stroke="oklch(0.65 0.19 260)"
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        name="AI debt score (min)"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Card>
              ) : (
                <Card className="mt-4 flex flex-col items-center gap-3 border-dashed p-6 text-center">
                  <p className="text-sm text-muted-foreground">
                    Analyse with history mode to see debt over time.
                  </p>
                  <Button
                    onClick={handleAnalyseHistory}
                    disabled={startingHistory || !result.repo_url}
                    title={result.repo_url ? undefined : "Original repo URL unknown (analysed before URL tracking)"}
                    size="sm"
                  >
                    {startingHistory ? "Starting…" : "Analyse with history mode"}
                  </Button>
                </Card>
              )}
            </>
          )}

          {debtTab === "sonar" && (
            <>
              {sonarAvailable && sonarData && sonarData.length >= 2 ? (
                <>
                  <Card className="mt-4 h-64 p-4">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={sonarData.map((p) => ({
                          date: p.commit_date.slice(0, 10),
                          sqale: p.sqale_index,
                        }))}
                        margin={{ top: 8, right: 16, bottom: 0, left: 0 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                        <XAxis dataKey="date" tick={{ fontSize: 11, fill: CHART_TICK }} />
                        <YAxis tick={{ fontSize: 11, fill: CHART_TICK }} />
                        <Tooltip
                          formatter={(value) => [`${Number(value).toLocaleString()} min`, "SQALE index"]}
                          contentStyle={{
                            background: "oklch(0.12 0 0)",
                            border: "1px solid oklch(1 0 0 / 12%)",
                            borderRadius: 8,
                            fontSize: 12,
                          }}
                          labelStyle={{ color: "oklch(0.708 0 0)" }}
                        />
                        <Line
                          type="monotone"
                          dataKey="sqale"
                          stroke="oklch(0.72 0.17 155)"
                          strokeWidth={2}
                          dot={{ r: 2 }}
                          name="SQALE index (min)"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </Card>
                  <p className="mt-2 text-xs text-muted-foreground">
                    SonarQube SQALE data from dissertation pipeline ·{" "}
                    {sonarData.length.toLocaleString()} commits ·{" "}
                    {sonarData.filter((p) => p.build_status === "BUILD_FAILED_SCAN_OK").length}{" "}
                    source-only scans
                  </p>
                </>
              ) : sonarAvailable === false ? (
                <Card className="mt-4 border-dashed p-6 text-center">
                  <p className="text-sm text-muted-foreground">
                    SonarQube pipeline data not yet available for this repo.
                  </p>
                </Card>
              ) : (
                <div className="mt-4 flex h-16 items-center justify-center">
                  <span className="size-5 animate-spin rounded-full border-2 border-emerald-500 border-t-transparent" />
                </div>
              )}
            </>
          )}
        </section>

        {result.churn_data && result.churn_data.top_churned_files.length > 0 && (
          <section className="mt-10">
            <h2 className="text-lg font-semibold">Churn hotspots</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Most frequently changed files across {result.churn_data.total_commits} commits.
              Hotspot threshold: {result.churn_data.hotspot_threshold}+ changes.
            </p>
            <Card className="mt-4 overflow-x-auto py-0">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-secondary/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-3 font-semibold">File</th>
                    <th className="px-4 py-3 font-semibold">Changes</th>
                    <th className="px-4 py-3 font-semibold">Authors</th>
                  </tr>
                </thead>
                <tbody>
                  {result.churn_data.top_churned_files.slice(0, 5).map((f) => (
                    <tr key={f.path} className="border-b border-border/60 last:border-0">
                      <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{f.path}</td>
                      <td className="px-4 py-2.5 tabular-nums">{f.change_count}</td>
                      <td className="px-4 py-2.5 tabular-nums">{f.author_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </section>
        )}

        <section className="mt-10 pb-16">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">
              Issues{" "}
              <span className="text-sm font-normal text-muted-foreground">
                ({filteredIssues.length} of {result.issues.length})
              </span>
            </h2>
            <div className="flex gap-2">
              <Select value={categoryFilter} onValueChange={(v) => setCategoryFilter(v ?? "all")}>
                <SelectTrigger size="sm" className="w-40">
                  <SelectValue placeholder="All categories" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All categories</SelectItem>
                  {categories.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c.replace(/_/g, " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={severityFilter} onValueChange={(v) => setSeverityFilter(v ?? "all")}>
                <SelectTrigger size="sm" className="w-36">
                  <SelectValue placeholder="All severities" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All severities</SelectItem>
                  {SEVERITY_ORDER.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="mt-4">
            <GroupedIssues issues={filteredIssues} />
          </div>
        </section>
      </main>
    </div>
  );
}
