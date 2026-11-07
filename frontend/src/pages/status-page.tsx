import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, LoaderCircle, RefreshCw, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, getHealth, getReady, readyErrorDetailsSchema } from "@/lib/api";

type RowState = "loading" | "ok" | "problem";

const DETAIL_TEXT: Record<string, string> = {
  unavailable: "Can't connect",
  behind: "Migrations need to run",
  unknown: "Can't check while the database is down",
};

function StatusRow({ label, state, text }: { label: string; state: RowState; text: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="font-medium">{label}</dt>
      <dd className="flex items-center gap-2 text-sm">
        {state === "loading" && (
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin text-muted-foreground" />
        )}
        {state === "ok" && <CheckCircle2 aria-hidden="true" className="size-4 text-success" />}
        {state === "problem" && <XCircle aria-hidden="true" className="size-4 text-destructive" />}
        <span className={state === "problem" ? "text-destructive" : undefined}>{text}</span>
      </dd>
    </div>
  );
}

function readinessRow(
  isPending: boolean,
  isSuccess: boolean,
  error: unknown,
  key: "database" | "migrations",
): { state: RowState; text: string } {
  if (isPending) return { state: "loading", text: "Checking…" };
  if (isSuccess) return { state: "ok", text: "OK" };

  const details =
    error instanceof ApiError ? readyErrorDetailsSchema.safeParse(error.details) : null;
  if (details?.success) {
    const value = details.data[key];
    if (value === "ok") return { state: "ok", text: "OK" };
    return { state: "problem", text: DETAIL_TEXT[value] ?? "Not ready" };
  }
  return { state: "problem", text: "Can't check" };
}

export function StatusPage() {
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth });
  const ready = useQuery({ queryKey: ["ready"], queryFn: getReady });

  const database = readinessRow(ready.isPending, ready.isSuccess, ready.error, "database");
  const migrations = readinessRow(ready.isPending, ready.isSuccess, ready.error, "migrations");
  const isFetching = health.isFetching || ready.isFetching;
  const requestError = [health.error, ready.error].find(
    (e): e is ApiError => e instanceof ApiError && e.code !== "not_ready",
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">System status</h1>
      <Card>
        <CardHeader>
          <CardTitle>Services</CardTitle>
          <CardDescription>Live results from the API's health checks.</CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="divide-y" aria-busy={isFetching}>
            <StatusRow
              label="API"
              state={health.isPending ? "loading" : health.isSuccess ? "ok" : "problem"}
              text={health.isPending ? "Checking…" : health.isSuccess ? "OK" : "Unavailable"}
            />
            <StatusRow label="Database" {...database} />
            <StatusRow label="Migrations" {...migrations} />
          </dl>
          {requestError && (
            <p role="alert" className="mt-4 text-sm text-destructive">
              {requestError.message}
            </p>
          )}
          <Button
            variant="outline"
            className="mt-4"
            disabled={isFetching}
            onClick={() => {
              void health.refetch();
              void ready.refetch();
            }}
          >
            <RefreshCw aria-hidden="true" />
            Check again
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
