import { describe, expect, it } from "vitest";
import { GRID_NODES_CONFIG, GRID_EDGES_CONFIG } from "./gridData";

describe("Grid Digital Twin Data & Logic", () => {
  it("contains all expected network topology nodes and edges", () => {
    const nodeKeys = Object.keys(GRID_NODES_CONFIG);
    expect(nodeKeys).toContain("utility");
    expect(nodeKeys).toContain("transformer");
    expect(nodeKeys).toContain("solar1");
    expect(nodeKeys).toContain("solar2");
    expect(nodeKeys).toContain("home");

    expect(GRID_EDGES_CONFIG.length).toBeGreaterThanOrEqual(4);
  });

  it("strictly preserves null telemetry in Missing data scenario (never converts to 0)", () => {
    for (const node of Object.values(GRID_NODES_CONFIG)) {
      const missingTelemetry = node.telemetry["Missing data"];
      expect(missingTelemetry.voltagePu).toBeNull();
      expect(missingTelemetry.voltageV).toBeNull();
      expect(missingTelemetry.activePowerKw).toBeNull();
      expect(missingTelemetry.loadingPct).toBeNull();
      expect(missingTelemetry.safetyMargin).toBeNull();
      expect(missingTelemetry.chipLabel).toBe("—");
    }
  });

  it("reflects overload on community transformer during congestion scenario", () => {
    const transformer = GRID_NODES_CONFIG.transformer;
    expect(transformer.telemetry.Congestion.loadingPct).toBe("108%");
    expect(transformer.telemetry.Congestion.voltagePu).toBe("0.91");
    expect(transformer.telemetry.Normal.loadingPct).toBe("64%");
    expect(transformer.telemetry.Normal.voltagePu).toBe("0.98");
  });

  it("includes correct physical ratings and electrical phase definitions", () => {
    expect(GRID_NODES_CONFIG.utility.phase).toContain("3-Phase 11 kV");
    expect(GRID_NODES_CONFIG.transformer.phase).toContain("3-Phase 415V");
    expect(GRID_NODES_CONFIG.solar1.phase).toContain("Single Phase");
    expect(GRID_NODES_CONFIG.home.phase).toContain("Single Phase");
  });
});
