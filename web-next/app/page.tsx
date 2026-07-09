"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FolderGit2, Sparkles, SquareCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { getRepos, startAnalysis, type RepoSummary } from "@/lib/api";

function severityStyles(score: number) {
  if (score < 500) {
    return {
      accent: "before:bg-emerald-500",
      iconBg: "bg-emerald-500/10",
      iconText: "text-emerald-400",
      badge: "bg-emerald-500/15 text-emerald-400",
    };
  }
  if (score <= 2000) {
    return {
      accent: "before:bg-amber-500",
      iconBg: "bg-amber-500/10",
      iconText: "text-amber-400",
      badge: "bg-amber-500/15 text-amber-400",
    };
  }
  return {
    accent: "before:bg-red-500",
    iconBg: "bg-red-500/10",
    iconText: "text-red-400",
    badge: "bg-red-500/15 text-red-400",
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
    <div className="relative min-h-screen overflow-hidden">
      <div className="bg-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_70%_50%_at_50%_0%,black_10%,transparent_70%)]" />
      <div className="pointer-events-none absolute left-1/2 top-[-12rem] h-[32rem] w-[64rem] -translate-x-1/2 rounded-full bg-blue-600/20 blur-[120px]" />

      <nav className="relative z-10 border-b border-border/60 bg-background/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-2xl items-center justify-between px-6 py-4">
          <span className="font-mono text-sm font-semibold tracking-tight">
            TD<span className="text-muted-foreground">/</span>agent
          </span>
          <a
            href="https://github.com/boluaj16/td-agent"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground"
          >
            <FolderGit2 className="size-4" />
            GitHub
          </a>
        </div>
      </nav>

      <main className="relative z-10 mx-auto max-w-2xl px-6 py-20">
        <div className="text-center">
          <Badge
            variant="outline"
            className="mx-auto mb-6 gap-1.5 border-border/80 bg-secondary/40 px-3 py-1 text-muted-foreground"
          >
            <Sparkles className="size-3 text-blue-400" />
            Powered by Gemini AI
          </Badge>

          <h1 className="text-5xl font-semibold tracking-tight sm:text-6xl">
            Find technical debt
            <br />
            before it finds{" "}
            <span className="bg-gradient-to-r from-blue-400 to-violet-400 bg-clip-text text-transparent">
              you
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-lg text-lg text-muted-foreground">
            Paste a GitHub URL. Get an AI debt score, natural language summary,
            and a full issue breakdown.
          </p>
        </div>

        <Card className="mx-auto mt-10 w-full max-w-xl p-2 shadow-2xl shadow-black/40">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
              className="h-12 flex-1 border-0 bg-transparent px-4 text-sm focus-visible:ring-0"
            />
            <Button
              type="submit"
              disabled={submitting}
              className="h-12 shrink-0 gap-1.5 rounded-lg px-6 text-sm font-semibold"
            >
              {submitting ? "Starting…" : "Analyse repo"}
              {!submitting && <ArrowRight className="size-4" />}
            </Button>
          </form>
        </Card>

        <div className="mx-auto mt-4 flex max-w-xl items-center justify-center gap-2.5">
          <Switch
            id="history-mode"
            size="sm"
            checked={includeHistory}
            onCheckedChange={setIncludeHistory}
          />
          <Label htmlFor="history-mode" className="text-xs font-normal text-muted-foreground">
            Include commit history (slower)
          </Label>
        </div>
        <p className="mx-auto mt-3 max-w-xl text-center text-xs text-muted-foreground/70">
          Free · No account required · Public repos only
        </p>
        {error && (
          <p className="mx-auto mt-3 max-w-xl text-center text-sm text-red-400">{error}</p>
        )}

        <section className="mt-20">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Recently analysed
          </h2>
          {reposLoaded && repos.length === 0 && (
            <p className="mt-4 text-sm text-muted-foreground">
              No repositories analysed yet — paste a URL above to get started.
            </p>
          )}
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {repos.map((r) => {
              const sev = severityStyles(r.latest_score);
              return (
                <a key={r.name} href={`/r/${r.name}`} className="group block">
                  <Card
                    className={`relative overflow-hidden py-4 pl-5 pr-4 transition before:absolute before:inset-y-0 before:left-0 before:w-[3px] ${sev.accent} group-hover:ring-foreground/20`}
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className={`flex size-8 shrink-0 items-center justify-center rounded-full ${sev.iconBg}`}
                      >
                        <SquareCode className={`size-4 ${sev.iconText}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate font-medium group-hover:text-blue-400">
                            {r.name}
                          </span>
                          <Badge className={`shrink-0 ${sev.badge}`} variant="secondary">
                            {r.latest_score.toLocaleString()}
                            <span className="font-normal opacity-70">min</span>
                          </Badge>
                        </div>
                        <p className="mt-1 truncate text-xs text-muted-foreground">
                          {r.issue_count} issues · last analysed {r.last_analysed}
                        </p>
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
