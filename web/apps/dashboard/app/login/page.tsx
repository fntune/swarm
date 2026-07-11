"use client";

import { Logo } from "@spawnd/ui/components/logo";
import { Button } from "@spawnd/ui/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@spawnd/ui/components/ui/card";
import { Input } from "@spawnd/ui/components/ui/input";
import { Label } from "@spawnd/ui/components/ui/label";
import { Loader2Icon } from "lucide-react";
import * as React from "react";

export default function LoginPage() {
  const [token, setToken] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      if (response.ok) {
        window.location.assign("/");
        return;
      }
      const body = (await response.json().catch(() => null)) as { error?: string } | null;
      setError(body?.error ?? `Login failed (status ${response.status})`);
    } catch {
      setError("Could not reach the dashboard server");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <Logo className="mb-2" />
          <CardTitle>Operator login</CardTitle>
          <CardDescription>
            Paste the deployed <code className="font-mono">SPAWND_API_TOKEN</code>. It is stored in
            an httpOnly cookie and only ever sent to the spawnd API from this server.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="token">API token</Label>
              <Input
                id="token"
                type="password"
                autoComplete="off"
                autoFocus
                required
                value={token}
                onChange={(event) => setToken(event.target.value)}
                className="font-mono"
                placeholder="••••••••••••••••"
              />
            </div>
            {error ? <p className="text-destructive text-sm">{error}</p> : null}
            <Button type="submit" disabled={busy || token.length === 0}>
              {busy ? <Loader2Icon className="size-4 animate-spin" /> : null}
              Sign in
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
