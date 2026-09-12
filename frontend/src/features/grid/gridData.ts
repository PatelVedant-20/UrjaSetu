import type { BaseGridNodeData, GridScenario, ScenarioMetrics } from "./types";

export interface TopologyNode {
  id: string;
  position: { x: number; y: number };
  baseData: BaseGridNodeData;
}

export const BASE_TOPOLOGY_NODES: TopologyNode[] = [
  {
    id: "utility",
    position: { x: 280, y: 0 },
    baseData: {
      id: "utility",
      busId: "BUS-11KV-001",
      externalRef: "DEMO-FEEDER-GJ-001",
      label: "DISCOM Substation",
      sublabel: "11 kV Utility Feeder · Slack Bus",
      nodeType: "feeder_substation",
      nominalVoltageKv: 11.0,
      ratedCapacityKw: 500,
      phaseConfig: "3-Phase 11 kV",
      operatingMode: "Grid-Forming / Slack Bus",
      connectionStatus: "Connected & Synchronized",
    },
  },
  {
    id: "transformer",
    position: { x: 280, y: 155 },
    baseData: {
      id: "transformer",
      busId: "BUS-LV-DTR-01",
      externalRef: "DEMO-DTR-GJ-001-A",
      label: "Community Transformer",
      sublabel: "100 kVA · 11 kV / 0.415 kV Step-Down (Dyn11)",
      nodeType: "distribution_transformer",
      nominalVoltageKv: 0.415,
      ratedCapacityKw: 100,
      phaseConfig: "3-Phase 415V",
      operatingMode: "Step-Down Distribution",
      connectionStatus: "Connected & Synchronized",
    },
  },
  {
    id: "solar1",
    position: { x: 30, y: 315 },
    baseData: {
      id: "solar1",
      busId: "BUS-LV-AARAV",
      externalRef: "DEMO-NODE-GJ-001-A-L1",
      label: "Aarav Residence",
      sublabel: "Rooftop PV · Smart Inverter",
      nodeType: "prosumer",
      nominalVoltageKv: 0.415,
      ratedCapacityKw: 8.0,
      phaseConfig: "3-Phase 415V",
      operatingMode: "Volt-VAR Active / Exporting",
      connectionStatus: "Synchronized",
      inverterModel: "SolarEdge SE8000H (Bi-directional)",
    },
  },
  {
    id: "solar2",
    position: { x: 280, y: 315 },
    baseData: {
      id: "solar2",
      busId: "BUS-LV-MEHTA",
      externalRef: "DEMO-NODE-GJ-001-A-L2",
      label: "Mehta Rooftop",
      sublabel: "Rooftop PV · Smart Inverter",
      nodeType: "prosumer",
      nominalVoltageKv: 0.23,
      ratedCapacityKw: 5.5,
      phaseConfig: "1-Phase 230V (Phase A)",
      operatingMode: "Volt-VAR Active / Exporting",
      connectionStatus: "Synchronized",
      inverterModel: "Enphase IQ8+ Microinverter",
    },
  },
  {
    id: "solar3",
    position: { x: 530, y: 315 },
    baseData: {
      id: "solar3",
      busId: "BUS-LV-PATEL",
      externalRef: "DEMO-NODE-GJ-001-A-L3",
      label: "Patel Residence",
      sublabel: "Rooftop PV · Hybrid Storage",
      nodeType: "prosumer",
      nominalVoltageKv: 0.23,
      ratedCapacityKw: 6.0,
      phaseConfig: "1-Phase 230V (Phase B)",
      operatingMode: "Self-Consumption & Export",
      connectionStatus: "Synchronized",
      inverterModel: "Growatt MIN 6000TL-X",
    },
  },
  {
    id: "home1",
    position: { x: 150, y: 475 },
    baseData: {
      id: "home1",
      busId: "BUS-LV-GREENVIEW",
      externalRef: "DEMO-NODE-GJ-001-A-L4",
      label: "Greenview Society",
      sublabel: "Residential Cluster Demand",
      nodeType: "consumer",
      nominalVoltageKv: 0.415,
      ratedCapacityKw: 18.0,
      phaseConfig: "3-Phase 415V",
      operatingMode: "Continuous Demand Point",
      connectionStatus: "Connected",
    },
  },
  {
    id: "home2",
    position: { x: 410, y: 475 },
    baseData: {
      id: "home2",
      busId: "BUS-LV-LIBRARY",
      externalRef: "DEMO-NODE-GJ-001-A-L5",
      label: "Community Library",
      sublabel: "Civic Demand & Study Hall",
      nodeType: "consumer",
      nominalVoltageKv: 0.23,
      ratedCapacityKw: 6.0,
      phaseConfig: "1-Phase 230V (Phase C)",
      operatingMode: "Continuous Demand Point",
      connectionStatus: "Connected",
    },
  },
];

export const SCENARIO_METRICS: Record<GridScenario, ScenarioMetrics> = {
  Normal: {
    validationOutcome: "Safe",
    validationOutcomeTone: "green",
    transformerLoadingPct: 64,
    minVoltagePu: 0.98,
    maxVoltagePu: 1.01,
    maxLineLoadingPct: 52,
    scenarioDescription:
      "Balanced daytime solar generation and community demand. All bus voltages remain within nominal 0.94–1.06 pu and transformer loading is comfortably within continuous limits.",
    inspectorMessage: "Example network state is within limits.",
  },
  Congestion: {
    validationOutcome: "Unsafe",
    validationOutcomeTone: "red",
    transformerLoadingPct: 108,
    minVoltagePu: 0.91,
    maxVoltagePu: 1.01,
    maxLineLoadingPct: 98,
    scenarioDescription:
      "Heavy residential demand causes transformer loading to exceed its continuous nameplate rating (108%) and terminal voltage to dip below the statutory minimum (0.91 pu vs 0.94 pu limit).",
    inspectorMessage: "Capacity exceeded. Do not commit a proposed trade.",
    violationsSummary: [
      "TRANSFORMER_OVERLOAD: 108% loading exceeds 100% continuous nameplate rating",
      "UNDER_VOLTAGE: Greenview Society terminal voltage dipped to 0.91 pu (limit 0.94 pu)",
      "LINE_OVERLOAD: Feeder lateral loading reaching 98% thermal threshold",
    ],
  },
  "Missing data": {
    validationOutcome: "Unknown",
    validationOutcomeTone: "amber",
    transformerLoadingPct: null,
    minVoltagePu: null,
    maxVoltagePu: null,
    maxLineLoadingPct: null,
    scenarioDescription:
      "Loss of smart meter telemetry and communication dropout across distribution feeder. Without authoritative voltage and power measurements, safety limits cannot be calculated.",
    inspectorMessage: "Missing measurements prevent a safety decision.",
    violationsSummary: [
      "OBSERVABILITY_LOSS: Missing telemetry packets from feeder smart meters",
      "INDETERMINATE_RISK: Automated gate blocks provisional trade commitment",
    ],
  },
  "Reverse power flow": {
    validationOutcome: "Warning",
    validationOutcomeTone: "amber",
    transformerLoadingPct: 72,
    minVoltagePu: 0.99,
    maxVoltagePu: 1.06,
    maxLineLoadingPct: 68,
    scenarioDescription:
      "Midday peak solar generation exceeds local feeder consumption; net surplus of 18.5 kW flows upstream through the transformer back into the 11 kV DISCOM grid, pushing prosumer terminals to the 1.06 pu statutory ceiling.",
    inspectorMessage:
      "Reverse power flow detected (18.5 kW backfeeding 11 kV grid). Voltages near 1.06 pu upper statutory limit.",
    violationsSummary: [
      "REVERSE_POWER_FLOW: Net 18.5 kW injection backfeeding distribution transformer",
      "VOLTAGE_RISE: Aarav Residence bus at 1.06 pu upper statutory boundary",
    ],
  },
};

export const SCENARIO_NODE_STATES: Record<
  GridScenario,
  Record<
    string,
    {
      currentVoltagePu: number | null;
      currentPowerKw: number | null;
      status: "safe" | "warning" | "unsafe" | "unknown";
      statusLabel: string;
      connectionStatus?: string;
      violations?: string[];
    }
  >
> = {
  Normal: {
    utility: {
      currentVoltagePu: 1.0,
      currentPowerKw: 28.5,
      status: "safe",
      statusLabel: "Normal Infeed",
    },
    transformer: {
      currentVoltagePu: 0.99,
      currentPowerKw: 28.5,
      status: "safe",
      statusLabel: "Nominal (64% Loading)",
    },
    solar1: {
      currentVoltagePu: 1.01,
      currentPowerKw: -6.2,
      status: "safe",
      statusLabel: "Exporting 6.2 kW",
    },
    solar2: {
      currentVoltagePu: 1.0,
      currentPowerKw: -4.1,
      status: "safe",
      statusLabel: "Exporting 4.1 kW",
    },
    solar3: {
      currentVoltagePu: 1.0,
      currentPowerKw: -4.8,
      status: "safe",
      statusLabel: "Exporting 4.8 kW",
    },
    home1: {
      currentVoltagePu: 0.98,
      currentPowerKw: 14.5,
      status: "safe",
      statusLabel: "Consuming 14.5 kW",
    },
    home2: {
      currentVoltagePu: 0.98,
      currentPowerKw: 4.8,
      status: "safe",
      statusLabel: "Consuming 4.8 kW",
    },
  },
  Congestion: {
    utility: {
      currentVoltagePu: 1.0,
      currentPowerKw: 108.0,
      status: "warning",
      statusLabel: "High Infeed Demand",
    },
    transformer: {
      currentVoltagePu: 0.95,
      currentPowerKw: 108.0,
      status: "unsafe",
      statusLabel: "Thermal Overload (108%)",
      violations: ["Loading at 108% exceeds continuous nameplate rating"],
    },
    solar1: {
      currentVoltagePu: 0.94,
      currentPowerKw: -1.5,
      status: "warning",
      statusLabel: "Low Irradiance / Droop Active",
    },
    solar2: {
      currentVoltagePu: 0.93,
      currentPowerKw: -0.8,
      status: "warning",
      statusLabel: "Under-Voltage Warning",
      violations: ["Voltage 0.93 pu is below 0.94 pu statutory limit"],
    },
    solar3: {
      currentVoltagePu: 0.92,
      currentPowerKw: 1.2,
      status: "warning",
      statusLabel: "Battery Discharging",
      violations: ["Voltage 0.92 pu is below 0.94 pu statutory limit"],
    },
    home1: {
      currentVoltagePu: 0.91,
      currentPowerKw: 22.0,
      status: "unsafe",
      statusLabel: "Under-Voltage (0.91 pu)",
      violations: [
        "Terminal voltage 0.91 pu violates 0.94 pu limit",
        "Lateral line loading at 98%",
      ],
    },
    home2: {
      currentVoltagePu: 0.92,
      currentPowerKw: 6.8,
      status: "warning",
      statusLabel: "Under-Voltage Warning",
      violations: ["Voltage 0.92 pu is below 0.94 pu statutory limit"],
    },
  },
  "Missing data": {
    utility: {
      currentVoltagePu: null,
      currentPowerKw: null,
      status: "unknown",
      statusLabel: "Observability Lost",
      connectionStatus: "Telemetry Unavailable",
    },
    transformer: {
      currentVoltagePu: null,
      currentPowerKw: null,
      status: "unknown",
      statusLabel: "No Metric Stream",
      connectionStatus: "Telemetry Unavailable",
    },
    solar1: {
      currentVoltagePu: null,
      currentPowerKw: null,
      status: "unknown",
      statusLabel: "Sensor Packet Loss",
      connectionStatus: "Offline",
    },
    solar2: {
      currentVoltagePu: null,
      currentPowerKw: null,
      status: "unknown",
      statusLabel: "Sensor Packet Loss",
      connectionStatus: "Offline",
    },
    solar3: {
      currentVoltagePu: null,
      currentPowerKw: null,
      status: "unknown",
      statusLabel: "Sensor Packet Loss",
      connectionStatus: "Offline",
    },
    home1: {
      currentVoltagePu: null,
      currentPowerKw: null,
      status: "unknown",
      statusLabel: "Meter Stale / Dropped",
      connectionStatus: "Offline",
    },
    home2: {
      currentVoltagePu: null,
      currentPowerKw: null,
      status: "unknown",
      statusLabel: "Meter Stale / Dropped",
      connectionStatus: "Offline",
    },
  },
  "Reverse power flow": {
    utility: {
      currentVoltagePu: 1.0,
      currentPowerKw: -18.5,
      status: "warning",
      statusLabel: "Grid Backfeed (-18.5 kW)",
    },
    transformer: {
      currentVoltagePu: 1.03,
      currentPowerKw: -18.5,
      status: "warning",
      statusLabel: "Reverse Flow Active",
      violations: [
        "Net surplus backfeeding 11 kV grid via distribution transformer",
      ],
    },
    solar1: {
      currentVoltagePu: 1.06,
      currentPowerKw: -7.8,
      status: "warning",
      statusLabel: "Peak Export / 1.06 pu Ceiling",
      violations: ["Terminal voltage at 1.06 pu statutory ceiling limit"],
    },
    solar2: {
      currentVoltagePu: 1.05,
      currentPowerKw: -5.2,
      status: "safe",
      statusLabel: "Full Generation (5.2 kW)",
    },
    solar3: {
      currentVoltagePu: 1.05,
      currentPowerKw: -5.8,
      status: "safe",
      statusLabel: "Full Generation (5.8 kW)",
    },
    home1: {
      currentVoltagePu: 1.01,
      currentPowerKw: 2.5,
      status: "safe",
      statusLabel: "Light Demand (2.5 kW)",
    },
    home2: {
      currentVoltagePu: 1.01,
      currentPowerKw: 1.8,
      status: "safe",
      statusLabel: "Light Demand (1.8 kW)",
    },
  },
};

export const TOPOLOGY_EDGES = [
  {
    id: "e-util-tx",
    source: "utility",
    target: "transformer",
    label: "11 kV Feeder (50 m)",
  },
  {
    id: "e-tx-solar1",
    source: "transformer",
    target: "solar1",
    label: "LV Feeder A",
  },
  {
    id: "e-tx-solar2",
    source: "transformer",
    target: "solar2",
    label: "LV Feeder B",
  },
  {
    id: "e-tx-solar3",
    source: "transformer",
    target: "solar3",
    label: "LV Feeder C",
  },
  {
    id: "e-tx-home1",
    source: "transformer",
    target: "home1",
    label: "Lateral 1",
  },
  {
    id: "e-tx-home2",
    source: "transformer",
    target: "home2",
    label: "Lateral 2",
  },
];
