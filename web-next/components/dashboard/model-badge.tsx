import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { PROVIDER_META } from "@/lib/provider";
import type { Provider } from "@/lib/api";

export function ModelBadge({
  model,
  provider,
  className,
}: {
  model: string;
  provider: Provider | "unknown";
  className?: string;
}) {
  const meta = PROVIDER_META[provider] ?? PROVIDER_META.unknown;
  return (
    <Badge
      variant="secondary"
      className={cn("max-w-full gap-1.5 font-mono font-normal", meta.badge, className)}
      title={`Analysed with ${model}`}
    >
      <span className={cn("size-1.5 shrink-0 rounded-full", meta.dot)} />
      <span className="truncate">{model || meta.label}</span>
    </Badge>
  );
}
