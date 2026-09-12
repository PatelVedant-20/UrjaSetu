import { describe, expect, it } from "vitest";
import {
  BASE_TOPOLOGY_NODES,
  SCENARIO_METRICS,
  SCENARIO_NODE_STATES,
  TOPOLOGY_EDGES,
} from "./gridData";
import type { GridScenario } from "./types";

describe("Grid Digital Twin Topology & Scenarios", () => {
  it("models the physical electrical hierarchy correctly", () => {
    const nodeTypes = BASE_TOPOLOGY_NODES.map((n) => n.baseData.nodeType);
    expect(nodeTypes).toContain("feeder_substation");
    expect(nodeTypes).toContain("distribution_transformer");
    expect(nodeTypes).toContain("prosumer");
    expect(nodeTypes).toContain("consumer");

    const substation = BASE_TOPOLOGY_NODES.find(
      (n) => n.baseData.nodeType === "feeder_substation",
    );
    expect(substation).toBeDefined();
    expect(substation?.baseData.nominalVoltageKv).toBe(11.0);
    expect(substation?.baseData.phaseConfig).toContain("11 kV");

    const dtr = BASE_TOPOLOGY_NODES.find(
      (n) => n.baseData.nodeType === "distribution_transformer",
    );
    expect(dtr).toBeDefined();
    expect(dtr?.baseData.nominalVoltageKv).toBe(0.415);
    expect(dtr?.baseData.ratedCapacityKw).toBe(100);

    const prosumers = BASE_TOPOLOGY_NODES.filter(
      (n) => n.baseData.nodeType === "prosumer",
    );
    expect(prosumers.length).toBeGreaterThanOrEqual(2);
    for (const p of prosumers) {
      expect(p.baseData.ratedCapacityKw).toBeGreaterThan(0);
      expect(p.baseData.inverterModel).toBeDefined();
    }

    const consumers = BASE_TOPOLOGY_NODES.filter(
      (n) => n.baseData.nodeType === "consumer",
    );
    expect(consumers.length).toBeGreaterThanOrEqual(2);
  });

  it("verifies distribution connectivity edges connect substation to DTR and DTR to loads", () => {
    const txEdge = TOPOLOGY_EDGES.find(
      (e) => e.source === "utility" && e.target === "transformer",
    );
    expect(txEdge).toBeDefined();

    const dtrOutgoing = TOPOLOGY_EDGES.filter(
      (e) => e.source === "transformer",
    );
    expect(dtrOutgoing.length).toBe(5); // 3 prosumers + 2 consumers
  });

  it("strictly preserves null measurements in Missing data scenario and never converts to zero", () => {
    const missingMetrics = SCENARIO_METRICS["Missing data"];
    expect(missingMetrics.transformerLoadingPct).toBeNull();
    expect(missingMetrics.minVoltagePu).toBeNull();
    expect(missingMetrics.maxVoltagePu).toBeNull();
    expect(missingMetrics.maxLineLoadingPct).toBeNull();
    expect(missingMetrics.validationOutcome).toBe("Unknown");
    expect(missingMetrics.inspectorMessage).toBe(
      "Missing measurements prevent a safety decision.",
    );

    const missingNodes = SCENARIO_NODE_STATES["Missing data"];
    for (const nodeId of Object.keys(missingNodes)) {
      expect(missingNodes[nodeId].currentVoltagePu).toBeNull();
      expect(missingNodes[nodeId].currentPowerKw).toBeNull();
      expect(missingNodes[nodeId].status).toBe("unknown");
    }
  });

  it("accurately models Congestion scenario with transformer overload and under-voltage violations", () => {
    const congestionMetrics = SCENARIO_METRICS["Congestion"];
    expect(congestionMetrics.validationOutcome).toBe("Unsafe");
    expect(congestionMetrics.transformerLoadingPct).toBe(108);
    expect(congestionMetrics.minVoltagePu).toBe(0.91);
    expect(congestionMetrics.maxLineLoadingPct).toBe(98);
    expect(congestionMetrics.violationsSummary).toBeDefined();
    expect(congestionMetrics.violationsSummary?.length).toBeGreaterThan(0);

    const dtrState = SCENARIO_NODE_STATES["Congestion"]["transformer"];
    expect(dtrState.status).toBe("unsafe");
    expect(dtrState.violations?.length).toBeGreaterThan(0);
  });

  it("accurately models Reverse power flow scenario with upstream backfeed and overvoltage ceiling", () => {
    const reverseMetrics = SCENARIO_METRICS["Reverse power flow"];
    expect(reverseMetrics.validationOutcome).toBe("Warning");
    expect(reverseMetrics.maxVoltagePu).toBe(1.06);
    expect(reverseMetrics.inspectorMessage).toContain(
      "Reverse power flow detected",
    );

    const solar1 = SCENARIO_NODE_STATES["Reverse power flow"]["solar1"];
    expect(solar1.currentVoltagePu).toBe(1.06);
    expect(solar1.currentPowerKw).toBeLessThan(0); // exporting
  });

  it("ensures every scenario has states defined for every topology node", () => {
    const scenarios: GridScenario[] = [
      "Normal",
      "Congestion",
      "Missing data",
      "Reverse power flow",
    ];

    for (const sc of scenarios) {
      const states = SCENARIO_NODE_STATES[sc];
      for (const node of BASE_TOPOLOGY_NODES) {
        expect(states[node.id]).toBeDefined();
        expect(states[node.id].statusLabel).toBeTruthy();
      }
    }
  });
});
