export type GridNodeType =
  "feeder_substation" | "distribution_transformer" | "prosumer" | "consumer";

export type NodeStatus = "safe" | "warning" | "unsafe" | "unknown";

export type GridScenario =
  "Normal" | "Congestion" | "Missing data" | "Reverse power flow";

export interface BaseGridNodeData {
  id: string;
  busId: string;
  externalRef: string;
  label: string;
  sublabel: string;
  nodeType: GridNodeType;
  nominalVoltageKv: number;
  ratedCapacityKw: number | null;
  phaseConfig: string;
  operatingMode: string;
  connectionStatus: string;
  inverterModel?: string;
}

export interface GridNodeData
  extends BaseGridNodeData, Record<string, unknown> {
  currentVoltagePu: number | null;
  currentPowerKw: number | null;
  powerFactor?: number | null;
  status: NodeStatus;
  statusLabel: string;
  violations?: string[];
}

export interface ScenarioMetrics {
  validationOutcome: string;
  validationOutcomeTone: "green" | "red" | "amber";
  transformerLoadingPct: number | null;
  minVoltagePu: number | null;
  maxVoltagePu: number | null;
  maxLineLoadingPct: number | null;
  scenarioDescription: string;
  inspectorMessage: string;
  violationsSummary?: string[];
}
