import { afterEach, describe, expect, it, vi } from "vitest";
import { DataForgeClient, problemFromResponse } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("problem detail handling", () => {
  it("preserves RFC 9457 problem extension members", async () => {
    const response = new Response(
      JSON.stringify({
        type: "https://dataforge.local/problems/advanced_mode_unavailable",
        title: "Advanced Mode Unavailable",
        status: 400,
        detail: "Provider key is missing.",
        error: "advanced_mode_unavailable",
      }),
      {
        status: 400,
        headers: { "content-type": "application/problem+json" },
      },
    );

    await expect(problemFromResponse(response)).resolves.toMatchObject({
      status: 400,
      error: "advanced_mode_unavailable",
      detail: "Provider key is missing.",
    });
  });

  it("extracts legacy FastAPI detail payloads without exposing wrappers to the UI", async () => {
    const response = new Response(
      JSON.stringify({
        detail: { error: "file_too_large", message: "Too large." },
      }),
      {
        status: 413,
        statusText: "Payload Too Large",
        headers: { "content-type": "application/json" },
      },
    );

    await expect(problemFromResponse(response)).resolves.toMatchObject({
      status: 413,
      error: "file_too_large",
      detail: "Too large.",
    });
  });

  it("posts accepted constraint ids to the analyze workflow", async () => {
    const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        calls.push({ input, init });
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }),
    );

    const client = new DataForgeClient("https://api.example.test");
    await client.analyze(
      new File(["id\n1"], "sample.csv", { type: "text/csv" }),
      true,
      ["cnd-1"],
    );

    expect(String(calls[0].input)).toContain("/api/analyze?advanced=true");
    const body = calls[0].init?.body;
    expect(body).toBeInstanceOf(FormData);
    expect((body as FormData).get("accepted_constraint_ids")).toBe("[\"cnd-1\"]");
  });
});
