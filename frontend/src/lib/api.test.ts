import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ApiError, apiGet } from "@/lib/api";
import { jsonResponse } from "@/test/render";

const schema = z.object({ value: z.number() });

function mockFetch(response: Response | Error) {
  const fn =
    response instanceof Error
      ? vi.fn().mockRejectedValue(response)
      : vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function catchApiError(promise: Promise<unknown>): Promise<ApiError> {
  const error = await promise.catch((e: unknown) => e);
  expect(error).toBeInstanceOf(ApiError);
  return error as ApiError;
}

describe("apiGet", () => {
  it("returns validated data", async () => {
    mockFetch(jsonResponse({ value: 1 }));
    await expect(apiGet("/x", schema)).resolves.toEqual({ value: 1 });
  });

  it("parses the API error format", async () => {
    mockFetch(
      jsonResponse(
        { error: { code: "already_exists", message: "It exists.", details: { field: "name" } } },
        409,
        { "X-Request-ID": "req-1" },
      ),
    );
    const error = await catchApiError(apiGet("/x", schema));
    expect(error.status).toBe(409);
    expect(error.code).toBe("already_exists");
    expect(error.message).toBe("It exists.");
    expect(error.details).toEqual({ field: "name" });
    expect(error.requestId).toBe("req-1");
  });

  it("handles an error response that isn't JSON", async () => {
    mockFetch(new Response("<html>Bad gateway</html>", { status: 502 }));
    const error = await catchApiError(apiGet("/x", schema));
    expect(error.status).toBe(502);
    expect(error.code).toBe("unexpected_error");
  });

  it("reports network failures", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    const error = await catchApiError(apiGet("/x", schema));
    expect(error.code).toBe("network_error");
    expect(error.status).toBe(0);
  });

  it("rejects a response that doesn't match the schema", async () => {
    mockFetch(jsonResponse({ value: "not a number" }));
    const error = await catchApiError(apiGet("/x", schema));
    expect(error.code).toBe("invalid_response");
  });
});
