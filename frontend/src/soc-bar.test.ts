import { describe, expect, it } from "vitest";

import { socFillStyle } from "./soc-bar.js";

describe("socFillStyle", () => {
  it("returns zero width when SOC is null or zero", () => {
    expect(socFillStyle(null, 20)).toBe("width:0%");
    expect(socFillStyle(0, 20)).toBe("width:0%");
  });

  it("includes blended ramp with background scaling", () => {
    const style = socFillStyle(50, 20);
    expect(style).toContain("width:50%");
    expect(style).toContain(
      "var(--bad) 0%,var(--bad) 20%,var(--accent) 52.5%,var(--good) 85%,var(--good) 100%",
    );
    expect(style).toContain("background-size:200% 100%");
    expect(style).toContain("background-repeat:no-repeat");
  });

  it("scales background when SOC is below min floor", () => {
    const style = socFillStyle(15, 20);
    expect(style).toContain("width:15%");
    expect(style).toContain(
      "var(--bad) 0%,var(--bad) 20%,var(--accent) 52.5%,var(--good) 85%,var(--good) 100%",
    );
    expect(style).toMatch(/background-size:\d+(\.\d+)?% 100%/);
  });

  it("clamps SOC above 100", () => {
    const style = socFillStyle(150, 20);
    expect(style).toContain("width:100%");
    expect(style).toContain("background-size:100% 100%");
  });

  it("handles min floor at 0 (no red zone)", () => {
    const style = socFillStyle(60, 0);
    expect(style).toContain("var(--accent) 0%,var(--good) 85%,var(--good) 100%");
    expect(style).not.toContain("var(--bad)");
  });

  it("handles min floor at 100 (all red)", () => {
    const style = socFillStyle(80, 100);
    expect(style).toContain("var(--bad) 0%,var(--bad) 100%");
    expect(style).not.toContain("var(--accent)");
  });

  it("clamps negative min floor and SOC", () => {
    const style = socFillStyle(-5, -10);
    expect(style).toBe("width:0%");
  });

  it("uses solid red plateau at min floor stop", () => {
    const style = socFillStyle(50, 20, 90);
    expect(style).toContain("var(--bad) 0%,var(--bad) 20%");
  });

  it("uses solid green plateau from max ceiling to 100%", () => {
    const style = socFillStyle(50, 20, 90);
    expect(style).toContain(
      "var(--bad) 0%,var(--bad) 20%,var(--accent) 52.5%,var(--good) 85%,var(--good) 100%",
    );
  });

  it("handles max ceiling below 100 with no red zone", () => {
    const style = socFillStyle(60, 0, 90);
    expect(style).toContain("var(--accent) 0%,var(--good) 85%,var(--good) 100%");
    expect(style).not.toContain("var(--bad)");
  });

  it("scales width when SOC is above max ceiling", () => {
    const style = socFillStyle(95, 20, 90);
    expect(style).toContain("width:95%");
    expect(style).toContain("var(--good) 85%,var(--good) 100%");
  });

  it("uses max ceiling as green start when below 85%", () => {
    const style = socFillStyle(60, 0, 70);
    expect(style).toContain("var(--accent) 0%,var(--good) 70%,var(--good) 100%");
    expect(style).not.toContain("var(--bad)");
  });

  it("shows solid green 85-100% band at full SOC", () => {
    const style = socFillStyle(100, 20);
    expect(style).toContain("width:100%");
    expect(style).toContain("var(--good) 85%,var(--good) 100%");
    expect(style).toContain("background-size:100% 100%");
  });
});
