"use client";

import { Button } from "@spawnd/ui/components/ui/button";
import { TriangleAlertIcon } from "lucide-react";

export default function ConsoleError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <TriangleAlertIcon className="size-8 text-status-failed" />
      <p className="font-medium text-sm">Something went wrong loading this view</p>
      <p className="max-w-md break-all font-mono text-muted-foreground text-xs">{error.message}</p>
      <Button variant="outline" size="sm" onClick={reset}>
        Retry
      </Button>
    </div>
  );
}
