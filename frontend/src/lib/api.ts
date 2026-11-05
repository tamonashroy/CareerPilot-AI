import { z } from "zod";

const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().optional(),
  }),
});

/** Every failure from the API client, whether from the server, the network or a bad response. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown = null,
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

export async function apiGet<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError(0, "network_error", "Could not reach the server.");
  }

  const requestId = response.headers.get("X-Request-ID");
  const body = await readJson(response);

  if (!response.ok) {
    const parsed = errorEnvelopeSchema.safeParse(body);
    if (parsed.success) {
      const { code, message, details } = parsed.data.error;
      throw new ApiError(response.status, code, message, details ?? null, requestId);
    }
    throw new ApiError(
      response.status,
      "unexpected_error",
      "The server returned an unexpected error.",
      null,
      requestId,
    );
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(
      response.status,
      "invalid_response",
      "The server returned an unexpected response.",
      null,
      requestId,
    );
  }
  return parsed.data;
}

const healthSchema = z.object({ status: z.literal("ok") });
const readySchema = z.object({
  status: z.literal("ready"),
  database: z.literal("ok"),
  migrations: z.literal("ok"),
});

export const readyErrorDetailsSchema = z.object({
  database: z.string(),
  migrations: z.string(),
});

export const getHealth = () => apiGet("/health", healthSchema);
export const getReady = () => apiGet("/ready", readySchema);
