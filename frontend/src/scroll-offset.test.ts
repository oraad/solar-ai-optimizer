import { describe, expect, it, vi } from "vitest";

import {
  readAppChromeHeightPx,
  releaseAfterProgrammaticScroll,
  sectionObserverRootMargin,
} from "./scroll-offset.js";

describe("scroll-offset", () => {
  it("readAppChromeHeightPx falls back when token missing", () => {
    expect(readAppChromeHeightPx(80)).toBe(80);
  });

  it("readAppChromeHeightPx parses --app-chrome-height from solar-app", () => {
    const app = document.createElement("solar-app");
    app.style.setProperty("--app-chrome-height", "96px");
    document.body.appendChild(app);
    expect(readAppChromeHeightPx()).toBe(96);
    app.remove();
  });

  it("sectionObserverRootMargin includes chrome and mobile nav inset", () => {
    const app = document.createElement("solar-app");
    app.style.setProperty("--app-chrome-height", "100px");
    document.body.appendChild(app);
    expect(sectionObserverRootMargin(40)).toBe("-148px 0px -60% 0px");
    app.remove();
  });

  it("releaseAfterProgrammaticScroll calls back immediately when reduced motion", () => {
    const onRelease = vi.fn();
    releaseAfterProgrammaticScroll(onRelease, true);
    expect(onRelease).toHaveBeenCalledTimes(1);
  });
});
