"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderGit2, LayoutDashboard, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { getRepos, type RepoSummary } from "@/lib/api";
import { scoreBand, SCORE_BAND_META } from "@/lib/severity";
import { useShell } from "./shell-context";

function NavLink({
  href,
  active,
  icon: Icon,
  children,
  onClick,
}: {
  href: string;
  active: boolean;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={cn(
        "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition",
        active
          ? "bg-secondary text-foreground"
          : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
      )}
    >
      <Icon className="size-4 shrink-0" />
      <span className="truncate">{children}</span>
    </Link>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const [repos, setRepos] = useState<RepoSummary[]>([]);

  useEffect(() => {
    getRepos()
      .then((r) => setRepos([...r].sort((a, b) => b.latest_score - a.latest_score)))
      .catch(() => setRepos([]));
  }, []);

  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border/60 px-4">
        <Link href="/" className="font-mono text-sm font-semibold tracking-tight" onClick={onNavigate}>
          TD<span className="text-muted-foreground">/</span>agent
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-4">
        <nav className="space-y-0.5">
          <NavLink href="/" active={pathname === "/"} icon={LayoutDashboard} onClick={onNavigate}>
            Overview
          </NavLink>
        </nav>

        <div className="mt-6">
          <p className="px-2.5 text-xs font-semibold uppercase tracking-widest text-muted-foreground/70">
            Repositories
          </p>
          <div className="mt-2 space-y-0.5">
            {repos.length === 0 && (
              <p className="px-2.5 text-xs text-muted-foreground/60">None analysed yet</p>
            )}
            {repos.map((r) => {
              const band = scoreBand(r.latest_score);
              const active = pathname === `/r/${r.name}`;
              return (
                <Link
                  key={r.name}
                  href={`/r/${r.name}`}
                  onClick={onNavigate}
                  className={cn(
                    "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm transition",
                    active
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                  )}
                >
                  <span className={cn("size-1.5 shrink-0 rounded-full", SCORE_BAND_META[band].dot)} />
                  <span className="truncate">{r.name}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-border/60 p-3">
        <a
          href="https://github.com/boluaj16/td-agent"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm text-muted-foreground transition hover:bg-secondary/60 hover:text-foreground"
        >
          <FolderGit2 className="size-4" />
          GitHub
        </a>
        <p className="mt-2 px-2.5 text-[0.65rem] leading-relaxed text-muted-foreground/50">
          MSc research · Leeds Beckett University
        </p>
      </div>
    </div>
  );
}

export function Sidebar() {
  const { mobileNavOpen, closeMobileNav } = useShell();

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-border/60 bg-sidebar lg:block">
        <SidebarContent />
      </aside>

      {/* Mobile sidebar + overlay */}
      <div
        className={cn(
          "fixed inset-0 z-50 lg:hidden",
          mobileNavOpen ? "pointer-events-auto" : "pointer-events-none",
        )}
      >
        <div
          className={cn(
            "absolute inset-0 bg-black/60 transition-opacity",
            mobileNavOpen ? "opacity-100" : "opacity-0",
          )}
          onClick={closeMobileNav}
        />
        <aside
          className={cn(
            "absolute inset-y-0 left-0 w-72 max-w-[85vw] border-r border-border/60 bg-sidebar shadow-2xl transition-transform",
            mobileNavOpen ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <button
            onClick={closeMobileNav}
            className="absolute right-3 top-3 flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
            aria-label="Close menu"
          >
            <X className="size-4" />
          </button>
          <SidebarContent onNavigate={closeMobileNav} />
        </aside>
      </div>
    </>
  );
}
