import { ChevronRight, Link2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Issue } from "@/lib/api";

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400",
  high: "bg-orange-500/15 text-orange-400",
  medium: "bg-yellow-500/15 text-yellow-400",
  low: "bg-emerald-500/15 text-emerald-400",
};

const CONFIDENCE_BADGE: Record<string, string> = {
  high: "bg-emerald-500/15 text-emerald-400",
  medium: "bg-yellow-500/15 text-yellow-400",
  low: "bg-red-500/15 text-red-400",
};

const SEVERITY_ORDER = ["critical", "high", "medium", "low"];

function IssueCard({ issue }: { issue: Issue }) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="capitalize">
          {issue.category.replace(/_/g, " ")}
        </Badge>
        <Badge className={cn("capitalize", SEVERITY_BADGE[issue.severity] ?? "bg-secondary")}>
          {issue.severity}
        </Badge>
        {issue.confidence && (
          <Badge className={CONFIDENCE_BADGE[issue.confidence] ?? "bg-secondary"}>
            {issue.confidence} confidence
          </Badge>
        )}
        <span className="ml-auto text-xs font-semibold text-muted-foreground">
          ~{issue.remediation_minutes} min to fix
        </span>
      </div>
      {issue.location && (
        <p className="mt-3 flex items-center gap-1 font-mono text-xs text-muted-foreground">
          <Link2 className="size-3" />
          {issue.location}
        </p>
      )}
      <p className="mt-2 text-sm leading-relaxed">{issue.description}</p>
      {issue.why_debt && (
        <p className="mt-2 text-sm italic leading-relaxed text-muted-foreground">{issue.why_debt}</p>
      )}
      {issue.suggestion && (
        <p className="mt-2 text-sm leading-relaxed text-blue-400">→ {issue.suggestion}</p>
      )}
    </Card>
  );
}

export function GroupedIssues({ issues }: { issues: Issue[] }) {
  const groups = new Map<string, Issue[]>();
  for (const issue of issues) {
    const list = groups.get(issue.category) ?? [];
    list.push(issue);
    groups.set(issue.category, list);
  }

  const sortedCategories = Array.from(groups.entries()).sort(
    ([, a], [, b]) =>
      b.reduce((s, i) => s + i.remediation_minutes, 0) - a.reduce((s, i) => s + i.remediation_minutes, 0),
  );

  return (
    <div className="space-y-3">
      {sortedCategories.map(([category, categoryIssues]) => {
        const totalMinutes = categoryIssues.reduce((s, i) => s + i.remediation_minutes, 0);
        const worstSeverity = SEVERITY_ORDER.find((sev) =>
          categoryIssues.some((i) => i.severity === sev),
        );
        return (
          <details key={category} className="group/details rounded-xl border border-border/60">
            <summary className="flex cursor-pointer list-none items-center gap-3 rounded-xl px-4 py-3 transition hover:bg-secondary/40">
              <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition group-open/details:rotate-90" />
              <span className="text-sm font-medium capitalize">{category.replace(/_/g, " ")}</span>
              <Badge variant="secondary" className="shrink-0">
                {categoryIssues.length} issue{categoryIssues.length === 1 ? "" : "s"}
              </Badge>
              {worstSeverity && (
                <Badge className={cn("shrink-0 capitalize", SEVERITY_BADGE[worstSeverity])}>
                  {worstSeverity}
                </Badge>
              )}
              <span className="ml-auto shrink-0 text-xs font-medium text-muted-foreground">
                ~{totalMinutes.toLocaleString()} min
              </span>
            </summary>
            <div className="space-y-3 border-t border-border/60 p-4">
              {categoryIssues.map((issue, idx) => (
                <IssueCard key={idx} issue={issue} />
              ))}
            </div>
          </details>
        );
      })}
      {sortedCategories.length === 0 && (
        <Card className="border-dashed p-6 text-center text-sm text-muted-foreground">
          No issues match the current filters.
        </Card>
      )}
    </div>
  );
}
