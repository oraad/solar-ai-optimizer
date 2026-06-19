import { describe, expect, it } from "vitest";
import { basePrefix } from "./api.js";

function setPath(pathname: string) {
  window.history.pushState({}, "", pathname);
}

describe("basePrefix", () => {
  it("returns ingress prefix without trailing slash", () => {
    setPath("/api/hassio_ingress/abc123");
    expect(basePrefix()).toBe("/api/hassio_ingress/abc123");
  });

  it("returns hassio ingress prefix when path has trailing segments", () => {
    setPath("/api/hassio_ingress/abc123/dashboard");
    expect(basePrefix()).toBe("/api/hassio_ingress/abc123");
  });

  it("returns hass_ingress prefix without trailing slash", () => {
    setPath("/api/ingress/solar_ai/");
    expect(basePrefix()).toBe("/api/ingress/solar_ai");
  });

  it("returns hass_ingress prefix when path has trailing segments", () => {
    setPath("/api/ingress/solar_ai/dashboard");
    expect(basePrefix()).toBe("/api/ingress/solar_ai");
  });

  it("strips trailing slash on standalone root", () => {
    setPath("/app/");
    expect(basePrefix()).toBe("/app");
  });

  it("returns empty string at site root", () => {
    setPath("/");
    expect(basePrefix()).toBe("");
  });
});
