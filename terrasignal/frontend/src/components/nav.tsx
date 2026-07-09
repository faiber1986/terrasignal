"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { useLocale, type Locale } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export function Nav() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { t } = useLocale();

  const LINKS = [
    { href: "/dashboard", label: t("nav.portfolio") },
    { href: "/risk", label: t("nav.riskQueue") },
    { href: "/pricing", label: t("nav.pricing") },
    { href: "/governance", label: t("nav.governance") },
  ];

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
          <LocaleSwitch />
          <ThemeToggle />
          {user && (
            <>
              <span className="text-ink-muted">
                {user.name} <span className="text-ink-faint">· {t(`roles.${user.role}`)}</span>
              </span>
              <button
                onClick={logout}
                className="rounded-md px-2 py-1 text-ink-muted hover:bg-surface-sunken"
              >
                {t("nav.signOut")}
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function LocaleSwitch() {
  const { locale, setLocale } = useLocale();
  const options: Locale[] = ["en", "es"];

  return (
    <div className="flex items-center rounded-md border border-surface-border p-0.5 text-xs font-medium">
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => setLocale(opt)}
          aria-pressed={locale === opt}
          className={cn(
            "rounded px-1.5 py-0.5 uppercase transition-colors",
            locale === opt ? "bg-brand text-white" : "text-ink-muted hover:text-ink",
          )}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useLocale();
  const isDark = theme === "dark";

  return (
    <button
      onClick={toggleTheme}
      aria-label={isDark ? t("themeToggle.light") : t("themeToggle.dark")}
      title={isDark ? t("themeToggle.light") : t("themeToggle.dark")}
      className="grid h-7 w-7 place-items-center rounded-md text-ink-muted hover:bg-surface-sunken hover:text-ink"
    >
      {isDark ? (
        <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden>
          <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
          <path
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden>
          <path
            fill="currentColor"
            d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 1020.354 15.354z"
          />
        </svg>
      )}
    </button>
  );
}
