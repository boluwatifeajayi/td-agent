import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { PROVIDER_META } from "@/lib/provider";
import { confidenceLabel } from "@/lib/confidence";
import type { ComparisonEntry, Provider } from "@/lib/api";

const SEVERITY_ORDER = ["critical", "high", "medium", "low"] as const;
const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-yellow-500",
  low: "bg-emerald-500",
};

function ProviderColumn({ provider, entry }: { provider: Provider; entry: ComparisonEntry }) {
  const meta = PROVIDER_META[provider];
  const totalIssues = entry.issue_count || 1;
  return (
    <div className="flex-1 rounded-lg border border-border/60 p-4">
      <div className="flex items-center gap-2">
        <span className={cn("size-2 rounded-full", meta.dot)} />
        <span className={cn("text-sm font-semibold", meta.text)}>{meta.label}</span>
        <span className="font-mono text-[11px] text-muted-foreground">{entry.model}</span>
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums">
        {entry.ai_debt_score.toLocaleString()}
        <span className="ml-1 text-sm font-normal text-muted-foreground">min</span>
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-muted-foreground">Issues</p>
          <p className="font-medium tabular-nums">{entry.issue_count}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Top category</p>
          <p className="truncate font-medium capitalize">
            {entry.top_category?.replace(/_/g, " ") ?? "—"}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Avg. confidence</p>
          <p className="font-medium">{confidenceLabel(entry.avg_confidence)}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Analysed</p>
          <p className="font-medium">{entry.commit_date.slice(0, 10)}</p>
        </div>
      </div>
      <div className="mt-3">
        <p className="text-xs text-muted-foreground">Severity mix</p>
        <div className="mt-1.5 flex h-2 w-full overflow-hidden rounded-full bg-secondary/60">
          {SEVERITY_ORDER.map((sev) => {
            const count = entry.severity_breakdown[sev] ?? 0;
            if (!count) return null;
            return (
              <div
                key={sev}
                className={SEVERITY_DOT[sev]}
                style={{ width: `${(count / totalIssues) * 100}%` }}
                title={`${sev}: ${count}`}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

export function ProviderComparison({
  comparison,
}: {
  comparison: Record<string, ComparisonEntry>;
}) {
  const providers = Object.keys(comparison) as Provider[];
  if (providers.length < 2) return null;

  const [a, b] = providers;
  const delta = comparison[a].ai_debt_score - comparison[b].ai_debt_score;

  return (
    <section className="mt-10">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Model comparison</h2>
        <p className="text-xs text-muted-foreground">
          {PROVIDER_META[a].label} vs {PROVIDER_META[b].label} on this repo ·{" "}
          <span className={delta === 0 ? "" : delta > 0 ? "text-red-400" : "text-emerald-400"}>
            {delta > 0 ? "+" : ""}
            {delta.toLocaleString()} min
          </span>
        </p>
      </div>
      <div className="mt-4 flex flex-col gap-4 sm:flex-row">
        {providers.map((p) => (
          <ProviderColumn key={p} provider={p} entry={comparison[p]} />
        ))}
      </div>
    </section>
  );
}
