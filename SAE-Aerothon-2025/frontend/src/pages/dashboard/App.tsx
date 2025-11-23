"use client";
import React, { useState, useEffect, useCallback } from "react";
import { DashboardLayout } from "../../components/DashboardLayout";
import { TelemetryWidget } from "../../components/TelemetryWidget";
import { MissionLogWidget } from "../../components/MissionLogWidget";
import { Navbar } from "./components/Navbar";
import { FleetOverview } from "@/components/FleetOverview";
import { VideoSource, SessionState, AnalysisResult, TelemetryData } from "@/types";
import { generateSessionId } from "@/lib/utils";
import { Activity, Battery, Gauge, Navigation, Zap, AlertTriangle, Brain } from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function GCSInterface() {
  // --- State ---
  const [videoSource, setVideoSource] = useState<VideoSource>({
    type: "Webcam",
    connectionString: "",
    isActive: false,
  });
  const [isConnected, setIsConnected] = useState(false);
  const [sessionState, setSessionState] = useState<SessionState>({
    session_id: "",
    frame_number: 0,
    is_recording: false,
    unique_objects: {},
    start_time: new Date(0),
    last_analysis: null,
    latency_ms: null,
  });
  const [telemetry, setTelemetry] = useState<TelemetryData | null>(null);
  const [aiReasoning, setAiReasoning] = useState<{ hazard: boolean, reasoning: string } | null>(null);
  const [missionEvents, setMissionEvents] = useState<any[]>([]);

  // Multi-drone state
  const [fleetStatus, setFleetStatus] = useState<any[]>([]);
  const [selectedDroneId, setSelectedDroneId] = useState<number>(1);

  // --- Effects ---
  useEffect(() => {
    setSessionState(prev => ({ ...prev, session_id: generateSessionId(), start_time: new Date() }));
  }, []);

  // Fleet Status Polling
  useEffect(() => {
    if (!isConnected) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/fleet/status`);
        if (res.ok) {
          const data = await res.json();
          setFleetStatus(data.drones || []);
        }
      } catch (e) {
        console.error("Fleet fetch error", e);
        // Don't crash, just keep trying
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [isConnected]);

  // Telemetry Polling (for selected drone)
  useEffect(() => {
    if (!isConnected) return;
    const interval = setInterval(async () => {
      try {
        // Try fleet endpoint first
        let res = await fetch(`${BACKEND_URL}/fleet/telemetry/${selectedDroneId}?session_id=${sessionState.session_id}`);

        // If 404, fallback to old endpoint for backward compatibility
        if (!res.ok && res.status === 404) {
          res = await fetch(`${BACKEND_URL}/telemetry/sensors?session_id=${sessionState.session_id}`);
        }

        if (res.ok) setTelemetry(await res.json());
      } catch (e) {
        console.error("Telemetry fetch error", e);
        // Don't crash, just keep trying
      }
    }, 1000);
    return () => clearInterval(interval);
  }, [isConnected, selectedDroneId, sessionState.session_id]);

  // WebSocket for AI Analysis and Mission Events
  useEffect(() => {
    if (!isConnected) return;

    const wsUrl = `${BACKEND_URL.replace('http', 'ws')}/ws/ai_analysis`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Add to mission events log
        setMissionEvents(prev => [...prev.slice(-49), { ...data, timestamp: data.timestamp || Date.now() / 1000 }]);

        // Update AI reasoning overlay if present
        if (data.reasoning) {
          setAiReasoning({
            hazard: data.disaster_detected || data.human_detected || false,
            reasoning: data.reasoning
          });
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
    };

    return () => {
      ws.close();
    };
  }, [isConnected]);

  // --- Handlers ---
  const handleConnect = useCallback(() => {
    setVideoSource(prev => ({ ...prev, isActive: true }));
    setIsConnected(true);
  }, []);

  const handleDisconnect = useCallback(() => {
    setVideoSource(prev => ({ ...prev, isActive: false }));
    setIsConnected(false);
  }, []);

  // --- Render ---
  return (
    <div className="h-screen bg-background text-foreground p-2 md:p-3 font-sans selection:bg-primary selection:text-primary-foreground overflow-hidden flex flex-col gap-1">
      {/* Top Bar (Navigation) - Outside grid, minimal space */}
      <div className="shrink-0">
        <Navbar
          videoSource={videoSource}
          onSourceChange={setVideoSource}
          onConnect={handleConnect}
          onDisconnect={handleDisconnect}
          isConnected={isConnected}
          drones={fleetStatus}
          selectedDrone={selectedDroneId}
          onSelectDrone={setSelectedDroneId}
        />
      </div>

      {/* Main Content Area - Grid Split, fills remaining space */}
      <div className="flex-1 grid grid-cols-1 md:grid-cols-12 gap-1 min-h-0">
        {/* Left Column: Video Feed + Mission Log (9 columns) */}
        <div className="col-span-1 md:col-span-9 flex flex-col gap-0 h-full min-h-0">
          {/* Video Feed - Takes most of the space */}
          <div className="flex-1 glass-panel rounded-xl overflow-hidden relative min-h-0">
            <div className="absolute top-4 left-4 z-10 flex gap-2">
              <div className="bg-black/50 backdrop-blur px-3 py-1 rounded text-xs font-mono text-primary border border-primary/30">
                LIVE FEED
              </div>
              {aiReasoning?.hazard && (
                <div className="bg-destructive/80 backdrop-blur px-3 py-1 rounded text-xs font-bold text-black animate-pulse flex items-center gap-1">
                  <AlertTriangle size={12} /> HAZARD DETECTED
                </div>
              )}
            </div>

            <div className="w-full h-full relative bg-black">
              {isConnected ? (
                <img src={`${BACKEND_URL}/video_feed`} className="absolute inset-0 w-full h-full object-contain" alt="Live Video Feed" />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                  <p>System Offline</p>
                </div>
              )}
            </div>

            {/* AI Overlay - Top right corner, not overlapping video */}
            {aiReasoning && (
              <div className="absolute top-4 right-4 max-w-xs bg-black/80 backdrop-blur p-2 rounded border-l-4 border-secondary">
                <div className="flex items-center gap-2 text-secondary mb-1">
                  <Brain size={12} />
                  <span className="text-[10px] font-bold uppercase">Gemini Analysis</span>
                </div>
                <p className="text-[10px] text-white line-clamp-3">{aiReasoning.reasoning}</p>
              </div>
            )}
          </div>

          {/* Mission Log - Below Video, fixed height */}
          <MissionLogWidget events={missionEvents} className="h-[150px] shrink-0" />
        </div>

        {/* Right: Telemetry & Mission Control - Scrollable if needed but compact */}
        <div className="col-span-1 md:col-span-3 h-full min-h-0 flex flex-col gap-3 overflow-y-auto pr-1">

          {/* Fleet Overview - At top of sidebar */}
          {fleetStatus.length > 0 && (
            <FleetOverview
              drones={fleetStatus}
              selectedDrone={selectedDroneId}
              onSelectDrone={setSelectedDroneId}
            />
          )}

          {/* Compact Telemetry Grid */}
          <div className="grid grid-cols-2 gap-2 shrink-0">
            <TelemetryWidget
              title="Alt"
              value={Number(telemetry?.gps?.altitude || 0).toFixed(1)}
              unit="m"
              icon={Navigation}
              data={[]}
              dataKey="alt"
              color="#00f3ff"
              className="h-32"
            />
            <TelemetryWidget
              title="Speed"
              value={Number(telemetry?.vfr_hud?.groundspeed || 0).toFixed(1)}
              unit="m/s"
              icon={Gauge}
              data={[]}
              dataKey="speed"
              color="#00f3ff"
              className="h-32"
            />
          </div>

          <TelemetryWidget
            title="Battery"
            value={Number(telemetry?.battery?.remaining || 0).toFixed(0)}
            unit="%"
            icon={Battery}
            color={telemetry?.battery?.remaining && telemetry.battery.remaining < 20 ? "#ffbd00" : "#00f3ff"}
            className="h-24 shrink-0"
          />

          {/* System Status - Compact */}
          <div className="glass-panel rounded-xl p-3 flex-1 min-h-[120px]">
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Activity size={16} />
              <span className="text-xs font-medium uppercase tracking-wider">System Status</span>
            </div>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">GPS Fix</span>
                <span className="text-white">{telemetry?.gps?.fix_type || "No Fix"}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Satellites</span>
                <span className="text-white">{telemetry?.gps?.satellites || 0}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Mode</span>
                <span className="text-primary font-bold">{telemetry?.status?.mode || "UNKNOWN"}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Armed</span>
                <span className={telemetry?.status?.armed ? "text-destructive font-bold" : "text-primary"}>
                  {telemetry?.status?.armed ? "ARMED" : "DISARMED"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
