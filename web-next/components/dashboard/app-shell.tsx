"use client";

import { Menu } from "lucide-react";
import { ShellProvider, useShell } from "./shell-context";
import { Sidebar } from "./sidebar";

function MobileMenuButton() {
  const { openMobileNav } = useShell();
  return (
    <button
      onClick={openMobileNav}
      className="fixed left-4 top-4 z-40 flex size-9 items-center justify-center rounded-lg border border-border/60 bg-card/90 text-foreground shadow-lg backdrop-blur-md lg:hidden"
      aria-label="Open menu"
    >
      <Menu className="size-4" />
    </button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ShellProvider>
      <Sidebar />
      <MobileMenuButton />
      <div className="lg:pl-64">{children}</div>
    </ShellProvider>
  );
}
