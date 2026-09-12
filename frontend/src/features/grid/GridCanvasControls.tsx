import { memo, useCallback } from "react";
import { useReactFlow, Panel } from "@xyflow/react";
import {
  Maximize2,
  Minimize2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Crosshair,
  Building2,
  Zap,
  Sun,
} from "lucide-react";

interface GridCanvasControlsProps {
  isFocused: boolean;
  onToggleFocus: () => void;
}

function GridCanvasControlsComponent({
  isFocused,
  onToggleFocus,
}: GridCanvasControlsProps) {
  const { fitView, setCenter, zoomIn, zoomOut } = useReactFlow();

  const handleOverview = useCallback(() => {
    fitView({ padding: 0.25, duration: 600 });
  }, [fitView]);

  const handleFocusSubstation = useCallback(() => {
    setCenter(300, 50, { zoom: 1.15, duration: 600 });
  }, [setCenter]);

  const handleFocusTransformer = useCallback(() => {
    setCenter(300, 190, { zoom: 1.25, duration: 600 });
  }, [setCenter]);

  const handleFocusProsumers = useCallback(() => {
    setCenter(300, 370, { zoom: 1.05, duration: 600 });
  }, [setCenter]);

  return (
    <>
      {/* Top Left View Presets Panel */}
      <Panel position="top-left" className="canvas-presets-panel">
        <span className="presets-label">CAMERA PRESETS:</span>
        <div className="preset-buttons-group">
          <button
            type="button"
            className="preset-btn"
            onClick={handleOverview}
            title="Fit All Grid Feeders"
          >
            <Crosshair size={12} />
            <span>Feeder Overview</span>
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={handleFocusSubstation}
            title="Focus Substation 11kV"
          >
            <Building2 size={12} />
            <span>11 kV Substation</span>
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={handleFocusTransformer}
            title="Focus Community Transformer"
          >
            <Zap size={12} />
            <span>Transformer</span>
          </button>
          <button
            type="button"
            className="preset-btn"
            onClick={handleFocusProsumers}
            title="Focus Rooftop Solar & Demand"
          >
            <Sun size={12} />
            <span>Prosumers & Demand</span>
          </button>
        </div>
      </Panel>

      {/* Top Right Quick Controls Panel */}
      <Panel position="top-right" className="canvas-quick-controls-panel">
        <div className="canvas-control-pill">
          <button
            type="button"
            className="canvas-icon-btn"
            onClick={() => zoomIn({ duration: 300 })}
            title="Zoom In"
            aria-label="Zoom in"
          >
            <ZoomIn size={14} />
          </button>
          <button
            type="button"
            className="canvas-icon-btn"
            onClick={() => zoomOut({ duration: 300 })}
            title="Zoom Out"
            aria-label="Zoom out"
          >
            <ZoomOut size={14} />
          </button>
          <button
            type="button"
            className="canvas-icon-btn"
            onClick={handleOverview}
            title="Reset to Fit View"
            aria-label="Reset to fit view"
          >
            <RotateCcw size={14} />
          </button>
          <div className="control-divider" />
          <button
            type="button"
            className={`canvas-icon-btn focus-toggle-btn ${isFocused ? "active" : ""}`}
            onClick={onToggleFocus}
            title={isFocused ? "Exit Focus Mode" : "Expand Canvas Focus Mode"}
            aria-label={
              isFocused ? "Exit Focus Mode" : "Expand Canvas Focus Mode"
            }
          >
            {isFocused ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            <span>{isFocused ? "Compact" : "Focus Mode"}</span>
          </button>
        </div>
      </Panel>
    </>
  );
}

export const GridCanvasControls = memo(GridCanvasControlsComponent);
