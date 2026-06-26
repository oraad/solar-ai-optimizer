import { afterEach, describe, expect, it } from "vitest";

import { TimezoneInput, ianaTimezones } from "./timezone-input.js";

function mount(value = "auto", resolvedHint = ""): TimezoneInput {
  const el = new TimezoneInput();
  el.value = value;
  el.resolvedHint = resolvedHint;
  document.body.appendChild(el);
  return el;
}

describe("TimezoneInput", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("lists auto and IANA zones in datalist", async () => {
    const el = mount();
    await el.updateComplete;
    const root = el.shadowRoot!;
    const options = [...root.querySelectorAll("datalist option")].map(
      (o) => (o as HTMLOptionElement).value,
    );
    expect(options[0]).toContain("Auto");
    expect(options).toContain("Africa/Johannesburg");
    expect(options.length).toBeGreaterThan(100);
  });

  it("preserves unknown saved timezone in datalist", async () => {
    const el = mount("Custom/Zone");
    await el.updateComplete;
    const options = [...el.shadowRoot!.querySelectorAll("datalist option")].map(
      (o) => (o as HTMLOptionElement).value,
    );
    expect(options).toContain("Custom/Zone");
  });

  it("emits timezone-change on commit", async () => {
    const el = mount();
    await el.updateComplete;
    let detail = "";
    el.addEventListener("timezone-change", (e) => {
      detail = (e as CustomEvent<string>).detail;
    });
    const input = el.shadowRoot!.querySelector("input") as HTMLInputElement;
    input.value = "Europe/Berlin";
    input.dispatchEvent(new Event("change"));
    expect(detail).toBe("Europe/Berlin");
  });

  it("shows resolved hint for auto mode", async () => {
    const el = mount("auto", "Africa/Johannesburg");
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).toContain("Africa/Johannesburg");
  });
});

describe("ianaTimezones", () => {
  it("returns sorted IANA names", () => {
    const zones = ianaTimezones();
    expect(zones.length).toBeGreaterThan(100);
    expect(zones).toContain("Africa/Johannesburg");
    expect(zones.indexOf("Africa/Johannesburg")).toBeLessThan(
      zones.indexOf("Europe/Berlin"),
    );
  });
});
