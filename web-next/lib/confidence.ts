export function confidenceLabel(avg: number | null): string {
  if (avg === null) return "—";
  if (avg >= 2.5) return "High";
  if (avg >= 1.5) return "Medium";
  return "Low";
}

export function confidenceColor(avg: number | null): string {
  if (avg === null) return "text-muted-foreground";
  if (avg >= 2.5) return "text-emerald-400";
  if (avg >= 1.5) return "text-yellow-400";
  return "text-red-400";
}
