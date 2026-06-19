import { afterEach, describe, expect, it, vi } from "vitest";
import { getApiToken, setApiToken } from "./api.js";

describe("API token storage", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("round-trips token via localStorage", () => {
    expect(getApiToken()).toBe("");
    setApiToken("secret");
    expect(getApiToken()).toBe("secret");
    setApiToken("");
    expect(getApiToken()).toBe("");
  });
});

describe("fetch error parsing", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("surfaces 401 hint when API token missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: "Unauthorized" }),
      }),
    );
    const { api } = await import("./api.js");
    await expect(api.status()).rejects.toThrow(/401.*API token/i);
  });
});
