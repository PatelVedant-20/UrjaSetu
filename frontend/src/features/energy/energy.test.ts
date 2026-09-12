import { describe, expect, it } from "vitest";
import {
  formatPowerKw,
  formatEnergyKwh,
  formatVoltagePu,
  resolveTelemetryTone,
  filterMembers,
} from "./energyUtils";
import { members } from "../../lib/demo";

describe("Energy & Telemetry Utils", () => {
  it("strictly distinguishes null power readings from zero", () => {
    expect(formatPowerKw(null)).toBe("Unavailable");
    expect(formatPowerKw(undefined)).toBe("Unavailable");
    expect(formatPowerKw("0")).toBe("0 kW");
    expect(formatPowerKw(0)).toBe("0 kW");
    expect(formatPowerKw("6.4")).toBe("6.4 kW");
  });

  it("strictly distinguishes null energy readings from zero", () => {
    expect(formatEnergyKwh(null)).toBe("Unavailable");
    expect(formatEnergyKwh(undefined)).toBe("Unavailable");
    expect(formatEnergyKwh("0")).toBe("0 kWh");
    expect(formatEnergyKwh(14.5)).toBe("14.5 kWh");
  });

  it("formats voltage in per-unit (pu) and handles nulls", () => {
    expect(formatVoltagePu(null)).toBe("Unavailable");
    expect(formatVoltagePu(1.02)).toBe("1.02 pu");
  });

  it("maps telemetry data-quality statuses to correct design tones", () => {
    expect(resolveTelemetryTone("valid")).toBe("green");
    expect(resolveTelemetryTone("stale")).toBe("amber");
    expect(resolveTelemetryTone("suspect")).toBe("amber");
    expect(resolveTelemetryTone("missing")).toBe("red");
    expect(resolveTelemetryTone("source_unavailable")).toBe("red");
    expect(resolveTelemetryTone("unknown")).toBe("neutral");
  });

  it("filters community members by query matching name or role", () => {
    const mehta = filterMembers(members, "Mehta");
    expect(mehta).toHaveLength(1);
    expect(mehta[0].name).toBe("Mehta Rooftop");

    const prosumers = filterMembers(members, "Prosumer");
    expect(prosumers.length).toBeGreaterThan(1);
  });
});
