"use client";
import React, { useState } from "react";
import { CesiumProvider } from "@/context/CesiumContext";
import CesiumGlobe from "./components/CesiumGlobe";
import TelemetryOverlay from "./components/TelemetryOverlay";
import MissionPlannerPanel from "./components/MissionPlannerPanel";
import WebcamPanel from "./components/WebcamPanel";

export default function HomeApp() {
  const [isVideoFullscreen, setIsVideoFullscreen] = useState(false);

  return (
    <CesiumProvider>
      <div className="relative w-full h-screen overflow-hidden">
        {/* Telemetry Overlay - always visible at top */}
        <div className="absolute inset-x-0 top-0 z-40">
          <TelemetryOverlay backendUrl="http://localhost:8000" />
        </div>

        {/* Globe - fullscreen when video is not, minimized when video is fullscreen */}
        <div
          className={`absolute transition-all duration-300 ${
            isVideoFullscreen
              ? "bottom-4 right-4 w-[400px] h-[300px] rounded-lg overflow-hidden shadow-2xl z-30 border-2 border-gray-600/50 bg-black/50 backdrop-blur-sm"
              : "inset-0 w-full h-full z-0"
          }`}
        >
          <div
            className={`absolute transition-transform duration-300 ${
              isVideoFullscreen ? "scale-[0.35] origin-top-left" : "inset-0"
            }`}
            style={
              isVideoFullscreen
                ? {
                    width: "100vw",
                    height: "100vh",
                    top: 0,
                    left: 0,
                  }
                : {}
            }
          >
            {/* Cesium Globe Background */}
            <CesiumGlobe />
          </div>

          {/* Click handler to restore */}
          {isVideoFullscreen && (
            <div
              className="absolute inset-0 z-50 cursor-pointer"
              onClick={() => setIsVideoFullscreen(false)}
              title="Click to restore map view"
            />
          )}
        </div>

        {/* Mission Planner Panel - hidden when video is fullscreen */}
        {!isVideoFullscreen && (
          <MissionPlannerPanel backendUrl="http://localhost:8000" />
        )}

        {/* Webcam Panel - shown as panel when not fullscreen, or fullscreen when toggled */}
        <WebcamPanel
          isFullscreen={isVideoFullscreen}
          onToggleFullscreen={() => setIsVideoFullscreen(!isVideoFullscreen)}
        />
      </div>
    </CesiumProvider>
  );
}
