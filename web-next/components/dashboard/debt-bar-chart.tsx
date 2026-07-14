"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "@/components/ui/card";
import type { RepoSummary } from "@/lib/api";
import { scoreBand, SCORE_BAND_META, type ScoreBand } from "@/lib/severity";

const CHART_TICK = "oklch(0.708 0 0)";

const LEGEND_ORDER: ScoreBand[] = ["low", "medium", "high"];

function truncateName(name: string, max = 14) {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: RepoSummary }[];
}) {
  if (!active || !payload?.length) return null;
  const repo = payload[0].payload;
  const band = scoreBand(repo.latest_score);
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-xl">
      <p className="font-medium text-foreground">{repo.name}</p>
      <p className="mt-1 text-muted-foreground">
        <span className={SCORE_BAND_META[band].text}>
          {repo.latest_score.toLocaleString()} min
        </span>{" "}
        · {repo.issue_count} issues
      </p>
    </div>
  );
}

export function DebtBarChart({ repos }: { repos: RepoSummary[] }) {
  const data = [...repos].sort((a, b) => b.latest_score - a.latest_score);
  const minWidth = Math.max(480, data.length * 76);

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">AI debt score by repository</p>
          <p className="text-xs text-muted-foreground">
            Estimated remediation time (minutes), most recent analysis
          </p>
        </div>
        <div className="flex items-center gap-3">
          {LEGEND_ORDER.map((band) => (
            <div key={band} className="flex items-center gap-1.5">
              <span className={`size-2 rounded-full ${SCORE_BAND_META[band].dot}`} />
              <span className="text-xs text-muted-foreground">{SCORE_BAND_META[band].label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <div style={{ height: 220, minWidth }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 20, right: 8, bottom: 4, left: 8 }} barCategoryGap={16}>
              <YAxis type="number" hide />
              <XAxis
                dataKey="name"
                tickLine={false}
                axisLine={false}
                interval={0}
                tick={{ fontSize: 11, fill: CHART_TICK }}
                tickFormatter={(name: string) => truncateName(name)}
              />
              <Tooltip cursor={{ fill: "oklch(1 0 0 / 4%)" }} content={<ChartTooltip />} />
              <Bar dataKey="latest_score" radius={[4, 4, 0, 0]} barSize={32}>
                {data.map((repo) => (
                  <Cell key={repo.name} fill={SCORE_BAND_META[scoreBand(repo.latest_score)].hex} />
                ))}
                <LabelList
                  dataKey="latest_score"
                  position="top"
                  formatter={(v: string | number | boolean | null | undefined) =>
                    typeof v === "number" ? v.toLocaleString() : v
                  }
                  style={{ fill: CHART_TICK, fontSize: 11 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {data.length === 0 && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          No repositories analysed yet.
        </p>
      )}
    </Card>
  );
}
