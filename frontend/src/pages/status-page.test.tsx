import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { jsonResponse, renderRoute } from "@/test/render";

type Responder = () => Promise<Response>;

function mockEndpoints(health: Responder, ready: Responder) {
  const fn = vi.fn((path: string) => (path === "/health" ? health() : ready()));
  vi.stubGlobal("fetch", fn);
  return fn;
}

const healthOk: Responder = async () => jsonResponse({ status: "ok" });
const readyOk: Responder = async () =>
  jsonResponse({ status: "ready", database: "ok", migrations: "ok" });

function notReady(database: string, migrations: string): Responder {
  return async () =>
    jsonResponse(
      {
        error: {
          code: "not_ready",
          message: "The service is not ready.",
          details: { database, migrations },
        },
      },
      503,
    );
}

function row(label: string) {
  return within(screen.getByText(label).parentElement!);
}

describe("StatusPage", () => {
  it("shows a loading state while checks are running", () => {
    const never: Responder = () => new Promise(() => {});
    mockEndpoints(never, never);
    renderRoute("/");
    expect(screen.getAllByText("Checking…")).toHaveLength(3);
  });

  it("shows every service as OK", async () => {
    mockEndpoints(healthOk, readyOk);
    renderRoute("/");
    expect(await row("Database").findByText("OK")).toBeInTheDocument();
    expect(await row("API").findByText("OK")).toBeInTheDocument();
    expect(row("Migrations").getByText("OK")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows when the database is down", async () => {
    mockEndpoints(healthOk, notReady("unavailable", "unknown"));
    renderRoute("/");
    expect(await row("Database").findByText("Can't connect")).toBeInTheDocument();
    expect(row("Migrations").getByText(/Can't check while/)).toBeInTheDocument();
    expect(await row("API").findByText("OK")).toBeInTheDocument();
  });

  it("shows when migrations are behind", async () => {
    mockEndpoints(healthOk, notReady("ok", "behind"));
    renderRoute("/");
    expect(await row("Migrations").findByText("Migrations need to run")).toBeInTheDocument();
    expect(row("Database").getByText("OK")).toBeInTheDocument();
  });

  it("shows an error when the API can't be reached", async () => {
    const offline: Responder = () => Promise.reject(new TypeError("Failed to fetch"));
    mockEndpoints(offline, offline);
    renderRoute("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
    expect(await row("API").findByText("Unavailable")).toBeInTheDocument();
  });

  it("checks again when asked", async () => {
    const fetchMock = mockEndpoints(healthOk, readyOk);
    renderRoute("/");
    await row("Database").findByText("OK");
    await row("API").findByText("OK");
    const callsBefore = fetchMock.mock.calls.length;

    await userEvent.click(await screen.findByRole("button", { name: "Check again" }));
    expect(fetchMock.mock.calls.length).toBe(callsBefore + 2);
  });
});
