export type ScoreBand = "low" | "medium" | "high";

export function scoreBand(score: number): ScoreBand {
  if (score < 500) return "low";
  if (score <= 2000) return "medium";
  return "high";
}

export const SCORE_BAND_META: Record<
  ScoreBand,
  { label: string; hex: string; dot: string; text: string; iconBg: string; badge: string; before: string }
> = {
  low: {
    label: "Low debt",
    hex: "#10b981",
    dot: "bg-emerald-500",
    text: "text-emerald-400",
    iconBg: "bg-emerald-500/10",
    badge: "bg-emerald-500/15 text-emerald-400",
    before: "before:bg-emerald-500",
  },
  medium: {
    label: "Moderate debt",
    hex: "#f59e0b",
    dot: "bg-amber-500",
    text: "text-amber-400",
    iconBg: "bg-amber-500/10",
    badge: "bg-amber-500/15 text-amber-400",
    before: "before:bg-amber-500",
  },
  high: {
    label: "High debt",
    hex: "#ef4444",
    dot: "bg-red-500",
    text: "text-red-400",
    iconBg: "bg-red-500/10",
    badge: "bg-red-500/15 text-red-400",
    before: "before:bg-red-500",
  },
};
