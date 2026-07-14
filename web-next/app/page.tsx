"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Bug, FolderGit2, Flame, Gauge, Sparkles, SquareCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { StatCard } from "@/components/dashboard/stat-card";
import { DebtBarChart } from "@/components/dashboard/debt-bar-chart";
import { cn } from "@/lib/utils";
import { scoreBand, SCORE_BAND_META } from "@/lib/severity";
import { getRepos, startAnalysis, type RepoSummary } from "@/lib/api";

function RiskSpotlight({ repo }: { repo: RepoSummary }) {
  const meta = SCORE_BAND_META[scoreBand(repo.latest_score)];
  return (
    <a href={`/r/${repo.name}`} className="group block">
      <Card className="p-5 transition group-hover:ring-foreground/20">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Highest risk
          </p>
          <Flame className={cn("size-3.5", meta.text)} />
        </div>
        <p className="mt-1.5 truncate text-xl font-semibold group-hover:text-blue-400">
          {repo.name}
        </p>
        <p className={cn("mt-1 text-xs font-medium", meta.text)}>
          {repo.latest_score.toLocaleString()} min · {meta.label}
        </p>
      </Card>
    </a>
  );
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

  const stats = useMemo(() => {
    if (repos.length === 0) return null;
    const totalIssues = repos.reduce((s, r) => s + r.issue_count, 0);
    const avgScore = Math.round(repos.reduce((s, r) => s + r.latest_score, 0) / repos.length);
    const riskiest = [...repos].sort((a, b) => b.latest_score - a.latest_score)[0];
    return { totalIssues, avgScore, riskiest };
  }, [repos]);

  const maxScore = useMemo(
    () => Math.max(1, ...repos.map((r) => r.latest_score)),
    [repos],
  );

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
    <div className="relative min-h-screen">
      <div className="bg-grid pointer-events-none absolute inset-0 opacity-40 [mask-image:radial-gradient(ellipse_70%_45%_at_50%_0%,black_10%,transparent_70%)]" />

      <main className="relative z-10 mx-auto max-w-6xl px-6 py-10 pt-16 lg:px-10 lg:pt-10">
        <div className="flex flex-col gap-6 border-b border-border/60 pb-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <Badge
              variant="outline"
              className="mb-3 gap-1.5 border-border/80 bg-secondary/40 px-2.5 py-0.5 text-muted-foreground"
            >
              <Sparkles className="size-3 text-blue-400" />
              Powered by Gemini AI
            </Badge>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Overview</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              AI-detected technical debt across all analysed repositories.
            </p>
          </div>

          <div className="w-full shrink-0 lg:w-[380px]">
            <Card className="p-2">
              <form onSubmit={handleSubmit} className="flex gap-2">
                <Input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                  required
                  className="h-9 flex-1 border-0 bg-transparent px-3 text-sm focus-visible:ring-0"
                />
                <Button type="submit" disabled={submitting} size="sm" className="shrink-0 gap-1.5 px-4">
                  {submitting ? "Starting…" : "Analyse"}
                  {!submitting && <ArrowRight className="size-3.5" />}
                </Button>
              </form>
            </Card>
            <div className="mt-2 flex items-center justify-between gap-2 px-1">
              <div className="flex items-center gap-2">
                <Switch
                  id="history-mode"
                  size="sm"
                  checked={includeHistory}
                  onCheckedChange={setIncludeHistory}
                />
                <Label htmlFor="history-mode" className="text-xs font-normal text-muted-foreground">
                  Include commit history
                </Label>
              </div>
              <span className="text-xs text-muted-foreground/60">Public repos only</span>
            </div>
            {error && <p className="mt-1.5 px-1 text-xs text-red-400">{error}</p>}
          </div>
        </div>

        {!reposLoaded && (
          <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-[92px] rounded-xl" />
            ))}
          </div>
        )}

        {reposLoaded && repos.length > 0 && stats && (
          <>
            <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard label="Repositories" value={repos.length} icon={FolderGit2} />
              <StatCard label="Total issues" value={stats.totalIssues} icon={Bug} />
              <StatCard
                label="Avg debt score"
                value={`${stats.avgScore.toLocaleString()} min`}
                icon={Gauge}
              />
              <RiskSpotlight repo={stats.riskiest} />
            </div>

            <div className="mt-6">
              <DebtBarChart repos={repos} />
            </div>
          </>
        )}

        <section className="mt-10 pb-16">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            All repositories
          </h2>
          {reposLoaded && repos.length === 0 && (
            <Card className="mt-4 border-dashed p-8 text-center">
              <p className="text-sm text-muted-foreground">
                No repositories analysed yet — paste a URL above to get started.
              </p>
            </Card>
          )}
          {!reposLoaded && (
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-[92px] rounded-xl" />
              ))}
            </div>
          )}
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {repos.map((r) => {
              const band = scoreBand(r.latest_score);
              const meta = SCORE_BAND_META[band];
              return (
                <a key={r.name} href={`/r/${r.name}`} className="group block">
                  <Card
                    className={cn(
                      "relative overflow-hidden py-4 pl-5 pr-4 transition before:absolute before:inset-y-0 before:left-0 before:w-[3px] group-hover:ring-foreground/20",
                      meta.before,
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div className={cn("flex size-8 shrink-0 items-center justify-center rounded-full", meta.iconBg)}>
                        <SquareCode className={cn("size-4", meta.text)} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate font-medium group-hover:text-blue-400">
                            {r.name}
                          </span>
                          <Badge className={cn("shrink-0", meta.badge)} variant="secondary">
                            {r.latest_score.toLocaleString()}
                            <span className="font-normal opacity-70">min</span>
                          </Badge>
                        </div>
                        <p className="mt-1 truncate text-xs text-muted-foreground">
                          {r.issue_count} issues · last analysed {r.last_analysed}
                        </p>
                        <div className="mt-2.5 h-1.5 w-full overflow-hidden rounded-full bg-secondary/60">
                          <div
                            className={cn("h-full rounded-full", meta.dot)}
                            style={{
                              width: `${Math.max(4, (r.latest_score / maxScore) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </Card>
                </a>
              );
            })}
          </div>
        </section>
      </main>

      <footer className="relative z-10 border-t border-border/60 py-8 text-center text-xs text-muted-foreground">
        TD Agent · Built for MSc research at Leeds Beckett University · Powered by Gemini AI
      </footer>
    </div>
  );
}
