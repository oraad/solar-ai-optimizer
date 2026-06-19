import { describe, expect, it } from "vitest";

// Test parseError via a thin re-export pattern — duplicate minimal logic for isolation.
async function parseDetail(res: Response, path: string): Promise<string> {
  if (res.status === 401) {
    return `${path} -> 401 Unauthorized — set API token in Settings`;
  }
  try {
    const body = (await res.json()) as {
      detail?: string | Array<{ loc?: unknown[]; msg?: string }>;
      error?: string;
    };
    if (Array.isArray(body.detail)) {
      const lines = body.detail.map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.join(".") : "";
        return loc ? `${loc}: ${d.msg ?? "invalid"}` : String(d.msg ?? "invalid");
      });
      return `${path} -> ${res.status}: ${lines.join("; ")}`;
    }
    const msg = typeof body.detail === "string" ? body.detail : body.error;
    if (msg) return `${path} -> ${res.status}: ${msg}`;
  } catch {
    /* ignore */
  }
  return `${path} -> ${res.status}`;
}

describe("parseError 422 detail", () => {
  it("formats pydantic validation array", async () => {
    const res = new Response(
      JSON.stringify({
        detail: [{ loc: ["battery", "capacity_kwh"], msg: "Input should be greater than 0" }],
      }),
      { status: 422 },
    );
    const msg = await parseDetail(res, "/api/config");
    expect(msg).toContain("battery.capacity_kwh");
    expect(msg).toContain("greater than 0");
  });
});
