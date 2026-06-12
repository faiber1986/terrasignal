"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { BaselineBanner } from "@/components/baseline-banner";
import { Nav } from "@/components/nav";
import { Spinner } from "@/components/ui/primitives";
import { useAuth } from "@/lib/auth";

/** Authenticated layout wrapper. Redirects to /login when there is no session.
 * The redirect is UX only — the backend rejects unauthenticated calls anyway. */
export function PageShell({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  if (!ready || !user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Nav />
      <BaselineBanner />
      <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
