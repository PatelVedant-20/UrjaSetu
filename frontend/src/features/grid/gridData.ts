export type GridScenario = "Normal" | "Congestion" | "Missing data";

export type GridNodeType = "substation" | "transformer" | "solar" | "demand";

export interface NodeTelemetry {
  voltagePu: string | null;
  voltageV: string | null;
  activePowerKw: string | null;
  loadingPct: string | null;
  powerFactor: string | null;
  frequencyHz: string | null;
  safetyMargin: string | null;
  chipLabel: string;
}

export interface GridNodeConfig {
  id: string;
  name: string;
  subtitle: string;
  type: GridNodeType;
  nominalVoltage: string;
  phase: string;
  ratedCapacity: string;
  iconName: "Building2" | "Zap" | "Sun" | "Home";
  initialPosition: { x: number; y: number };
  telemetry: Record<GridScenario, NodeTelemetry>;
}

export const GRID_NODES_CONFIG: Record<string, GridNodeConfig> = {
  utility: {
    id: "utility",
    name: "DISCOM Substation",
    subtitle: "11 kV Distribution Feeder",
    type: "substation",
    nominalVoltage: "11.0 kV",
    phase: "3-Phase 11 kV (MV Feeder)",
    ratedCapacity: "500 kVA",
    iconName: "Building2",
    initialPosition: { x: 300, y: 15 },
    telemetry: {
      Normal: {
        voltagePu: "1.00",
        voltageV: "11.00 kV",
        activePowerKw: "142.0",
        loadingPct: "28%",
        powerFactor: "0.99 lag",
        frequencyHz: "50.02 Hz",
        safetyMargin: "+72% Feeder Headroom",
        chipLabel: "1.00 pu · 28% load",
      },
      Congestion: {
        voltagePu: "0.96",
        voltageV: "10.56 kV",
        activePowerKw: "465.0",
        loadingPct: "93%",
        powerFactor: "0.92 lag",
        frequencyHz: "49.88 Hz",
        safetyMargin: "+7% Critical Headroom",
        chipLabel: "0.96 pu · 93% load",
      },
      "Missing data": {
        voltagePu: null,
        voltageV: null,
        activePowerKw: null,
        loadingPct: null,
        powerFactor: null,
        frequencyHz: null,
        safetyMargin: null,
        chipLabel: "—",
      },
    },
  },
  transformer: {
    id: "transformer",
    name: "Community transformer",
    subtitle: "Step-Down 11 kV / 0.415 kV",
    type: "transformer",
    nominalVoltage: "415 V / 240 V",
    phase: "3-Phase 415V Delta-Wye",
    ratedCapacity: "100 kVA",
    iconName: "Zap",
    initialPosition: { x: 300, y: 175 },
    telemetry: {
      Normal: {
        voltagePu: "0.98",
        voltageV: "406.7 V",
        activePowerKw: "64.0",
        loadingPct: "64%",
        powerFactor: "0.97 lag",
        frequencyHz: "50.01 Hz",
        safetyMargin: "36% Thermal Headroom",
        chipLabel: "0.98 pu · 64% load",
      },
      Congestion: {
        voltagePu: "0.91",
        voltageV: "377.6 V",
        activePowerKw: "108.0",
        loadingPct: "108%",
        powerFactor: "0.88 lag",
        frequencyHz: "49.85 Hz",
        safetyMargin: "-8% Overload Hazard",
        chipLabel: "0.91 pu · 108% load",
      },
      "Missing data": {
        voltagePu: null,
        voltageV: null,
        activePowerKw: null,
        loadingPct: null,
        powerFactor: null,
        frequencyHz: null,
        safetyMargin: null,
        chipLabel: "—",
      },
    },
  },
  solar1: {
    id: "solar1",
    name: "Aarav · Rooftop PV",
    subtitle: "Prosumer Grid-Tie Solar",
    type: "solar",
    nominalVoltage: "230 V",
    phase: "Single Phase L-N (Phase R)",
    ratedCapacity: "5.0 kW Inverter",
    iconName: "Sun",
    initialPosition: { x: 40, y: 350 },
    telemetry: {
      Normal: {
        voltagePu: "1.01",
        voltageV: "232.3 V",
        activePowerKw: "4.2",
        loadingPct: "84%",
        powerFactor: "1.00 unity",
        frequencyHz: "50.00 Hz",
        safetyMargin: "Export Within Limits",
        chipLabel: "1.01 pu · 4.2 kW gen",
      },
      Congestion: {
        voltagePu: "1.05",
        voltageV: "241.5 V",
        activePowerKw: "4.9",
        loadingPct: "98%",
        powerFactor: "0.98 cap",
        frequencyHz: "49.89 Hz",
        safetyMargin: "Overvoltage Curtailment Risk",
        chipLabel: "1.05 pu · 4.9 kW gen",
      },
      "Missing data": {
        voltagePu: null,
        voltageV: null,
        activePowerKw: null,
        loadingPct: null,
        powerFactor: null,
        frequencyHz: null,
        safetyMargin: null,
        chipLabel: "—",
      },
    },
  },
  solar2: {
    id: "solar2",
    name: "Mehta · Rooftop PV",
    subtitle: "Prosumer Grid-Tie Solar",
    type: "solar",
    nominalVoltage: "230 V",
    phase: "Single Phase L-N (Phase Y)",
    ratedCapacity: "4.0 kW Inverter",
    iconName: "Sun",
    initialPosition: { x: 300, y: 350 },
    telemetry: {
      Normal: {
        voltagePu: "1.00",
        voltageV: "230.0 V",
        activePowerKw: "3.8",
        loadingPct: "95%",
        powerFactor: "1.00 unity",
        frequencyHz: "50.01 Hz",
        safetyMargin: "Export Within Limits",
        chipLabel: "1.00 pu · 3.8 kW gen",
      },
      Congestion: {
        voltagePu: "1.04",
        voltageV: "239.2 V",
        activePowerKw: "4.0",
        loadingPct: "100%",
        powerFactor: "0.97 cap",
        frequencyHz: "49.90 Hz",
        safetyMargin: "Inverter Thermal Saturation",
        chipLabel: "1.04 pu · 4.0 kW gen",
      },
      "Missing data": {
        voltagePu: null,
        voltageV: null,
        activePowerKw: null,
        loadingPct: null,
        powerFactor: null,
        frequencyHz: null,
        safetyMargin: null,
        chipLabel: "—",
      },
    },
  },
  home: {
    id: "home",
    name: "Greenview · Demand",
    subtitle: "Household Community Consumption",
    type: "demand",
    nominalVoltage: "230 V",
    phase: "Single Phase L-N (Phase B)",
    ratedCapacity: "15.0 kW Sanctioned Load",
    iconName: "Home",
    initialPosition: { x: 560, y: 350 },
    telemetry: {
      Normal: {
        voltagePu: "0.98",
        voltageV: "225.4 V",
        activePowerKw: "5.1",
        loadingPct: "34%",
        powerFactor: "0.96 lag",
        frequencyHz: "50.00 Hz",
        safetyMargin: "+66% Headroom Available",
        chipLabel: "0.98 pu · 5.1 kW load",
      },
      Congestion: {
        voltagePu: "0.91",
        voltageV: "209.3 V",
        activePowerKw: "14.2",
        loadingPct: "95%",
        powerFactor: "0.86 lag",
        frequencyHz: "49.84 Hz",
        safetyMargin: "Severe Voltage Sag (0.91 pu)",
        chipLabel: "0.91 pu · 14.2 kW load",
      },
      "Missing data": {
        voltagePu: null,
        voltageV: null,
        activePowerKw: null,
        loadingPct: null,
        powerFactor: null,
        frequencyHz: null,
        safetyMargin: null,
        chipLabel: "—",
      },
    },
  },
};

export interface GridEdgeConfig {
  id: string;
  source: string;
  target: string;
  label?: string;
  phaseCode: string;
}

export const GRID_EDGES_CONFIG: GridEdgeConfig[] = [
  {
    id: "e-utility-transformer",
    source: "utility",
    target: "transformer",
    label: "11 kV / 0.415 kV MV Feeder",
    phaseCode: "3Φ MV",
  },
  {
    id: "e-transformer-solar1",
    source: "transformer",
    target: "solar1",
    label: "Phase R Feeder (230V)",
    phaseCode: "1Φ R",
  },
  {
    id: "e-transformer-solar2",
    source: "transformer",
    target: "solar2",
    label: "Phase Y Feeder (230V)",
    phaseCode: "1Φ Y",
  },
  {
    id: "e-transformer-home",
    source: "transformer",
    target: "home",
    label: "Phase B Feeder (230V)",
    phaseCode: "1Φ B",
  },
];
