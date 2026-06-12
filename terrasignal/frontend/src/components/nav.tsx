"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/dashboard", label: "Portfolio" },
  { href: "/risk", label: "Risk Queue" },
  { href: "/pricing", label: "Pricing" },
  { href: "/governance", label: "Governance" },
];

export function Nav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <header className="border-b border-surface-border bg-surface">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-6 px-6">
        <Link href="/dashboard" className="flex items-center gap-2 font-semibold text-ink">
          <span className="grid h-6 w-6 place-items-center rounded bg-brand text-xs text-white">
            TS
          </span>
          TerraSignal
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map((l) => {
            const active = pathname === l.href || pathname.startsWith(`${l.href}/`);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                  active ? "bg-surface-sunken text-ink" : "text-ink-muted hover:text-ink",
                )}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          {user && (
            <>
              <span className="text-ink-muted">
                {user.name} <span className="text-ink-faint">· {user.role}</span>
              </span>
              <button
                onClick={logout}
                className="rounded-md px-2 py-1 text-ink-muted hover:bg-surface-sunken"
              >
                Sign out
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
