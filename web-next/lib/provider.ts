import type { Provider } from "@/lib/api";

export const PROVIDER_META: Record<
  Provider | "unknown",
  { label: string; badge: string; dot: string; text: string }
> = {
  gemini: {
    label: "Gemini",
    badge: "bg-blue-500/15 text-blue-400",
    dot: "bg-blue-500",
    text: "text-blue-400",
  },
  claude: {
    label: "Claude",
    badge: "bg-orange-500/15 text-orange-400",
    dot: "bg-orange-500",
    text: "text-orange-400",
  },
  unknown: {
    label: "Unknown",
    badge: "bg-secondary text-muted-foreground",
    dot: "bg-muted-foreground",
    text: "text-muted-foreground",
  },
};
