"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, Card, CardBody, ErrorNote, Input, Label } from "@/components/ui/primitives";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { useLocale } from "@/lib/i18n";

export default function LoginPage() {
  const { user, ready, login } = useAuth();
  const { t } = useLocale();
  const router = useRouter();
  const [username, setUsername] = useState("ana.analyst");
  const [password, setPassword] = useState("demo");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const DEMO_USERS = [
    { username: "ana.analyst", role: t("login.demoAnalyst") },
    { username: "alex.approver", role: t("login.demoApprover") },
    { username: "admin", role: t("login.demoAdmin") },
  ];

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("login.signInFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-surface-sunken px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 grid h-10 w-10 place-items-center rounded-lg bg-brand text-sm font-semibold text-white">
            TS
          </div>
          <h1 className="text-lg font-semibold text-ink">TerraSignal</h1>
          <p className="text-sm text-ink-muted">{t("login.tagline")}</p>
        </div>
        <Card>
          <CardBody>
            <form onSubmit={onSubmit} className="space-y-3">
              <div>
                <Label htmlFor="username">{t("login.username")}</Label>
                <Input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor="password">{t("login.password")}</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  className="mt-1"
                />
              </div>
              {error && <ErrorNote>{error}</ErrorNote>}
              <Button type="submit" disabled={busy} className="w-full">
                {busy ? t("login.signingIn") : t("login.signIn")}
              </Button>
            </form>
          </CardBody>
        </Card>
        <div className="mt-4 space-y-1 rounded-md border border-surface-border bg-surface p-3 text-xs text-ink-muted">
          <p className="font-medium text-ink">{t("login.demoUsers")}</p>
          {DEMO_USERS.map((u) => (
            <button
              key={u.username}
              onClick={() => setUsername(u.username)}
              className="block w-full text-left hover:text-ink"
            >
              <span className="tnum font-medium">{u.username}</span> — {u.role}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
