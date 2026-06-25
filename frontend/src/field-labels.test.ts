import { beforeEach, describe, expect, it } from "vitest";

import { initI18n, setLocale } from "./i18n.js";
import {
  capabilityLabel,
  entityLabel,
  fieldLabel,
  gridChargeFactorLabel,
  optimizationPriorityLabel,
  sectionTitle,
} from "./field-labels.js";

describe("fieldLabel", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns mapped labels for known keys", () => {
    expect(fieldLabel("temperature", "hdd_base_c")).toBe("Heating base temperature (°C)");
    expect(fieldLabel("reserve", "critical_load_w")).toBe("Critical load (W)");
    expect(fieldLabel("control", "loop_interval_seconds")).toBe("Control loop interval (s)");
    expect(fieldLabel("load_shedding", "shed_below_soc")).toBe("Shed below SOC (%)");
    expect(fieldLabel("grid_charge", "battery_power")).toBe("Battery charge rate");
    expect(fieldLabel("battery", "round_trip_efficiency")).toBe("Round-trip efficiency");
    expect(fieldLabel("reserve", "cloudy_extra_buffer_pct")).toBe("Cloudy extra buffer (%)");
  });

  it("title-cases unknown keys", () => {
    expect(fieldLabel("battery", "some_new_field")).toBe("Some New Field");
  });
});

describe("sectionTitle", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns mapped section titles", () => {
    expect(sectionTitle("load_shedding")).toBe("Load shedding");
    expect(sectionTitle("engine")).toBe("Engine");
  });

  it("title-cases unknown sections", () => {
    expect(sectionTitle("custom_section")).toBe("Custom Section");
  });
});

describe("entityLabel", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns inverter entity labels with units for measurable quantities", () => {
    expect(entityLabel("battery_soc")).toBe("Battery state of charge (%)");
    expect(entityLabel("pv_power")).toBe("PV power (W)");
    expect(entityLabel("battery_temp")).toBe("Battery temperature (°C)");
    expect(entityLabel("max_grid_charge_current")).toBe("Max grid charge current (A)");
  });

  it("omits units for binary, switch, and select entities", () => {
    expect(entityLabel("grid_present")).toBe("Grid present sensor");
    expect(entityLabel("grid_charge_enable")).toBe("Grid charge enable");
    expect(entityLabel("grid_present")).not.toMatch(/\([%WA°C]+\)/);
  });

  it("falls back for unknown entities", () => {
    expect(entityLabel("custom_sensor")).toBe("Custom Sensor");
  });
});

describe("temperature entity label", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("includes degrees Celsius for outdoor sensor", () => {
    expect(fieldLabel("temperature", "ha_entity")).toBe("Outdoor temperature sensor (°C)");
  });
});

describe("capabilityLabel", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns human labels for write capabilities", () => {
    expect(capabilityLabel("max_grid_charge_current")).toBe("Max grid charge current (A)");
  });
});

describe("gridChargeFactorLabel", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns factor labels", () => {
    expect(gridChargeFactorLabel("soc_gap")).toBe("SOC gap to reserve");
  });
});

describe("optimizationPriorityLabel", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns priority labels", () => {
    expect(optimizationPriorityLabel("resilience")).toBe("Resilience");
    expect(optimizationPriorityLabel("self_sufficiency")).toBe("Self-sufficiency");
  });
});
