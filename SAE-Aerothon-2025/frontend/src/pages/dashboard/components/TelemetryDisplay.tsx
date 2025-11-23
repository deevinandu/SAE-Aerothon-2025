"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Navigation, Battery, Activity, Gauge, Clock, Zap } from "lucide-react";
import { TelemetryData } from "@/types";

interface TelemetryDisplayProps {
  backendUrl: string;
  sessionId?: string;
  refreshInterval?: number; // milliseconds
}

export function TelemetryDisplay({
  backendUrl,
  sessionId,
  refreshInterval = 1000,
}: TelemetryDisplayProps) {
  const [telemetryData, setTelemetryData] = useState<TelemetryData | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchTelemetryData = async () => {
    try {
      setIsLoading(true);
      setError(null);

      const url = `${backendUrl}/telemetry/sensors${
        sessionId ? `?session_id=${sessionId}` : ""
      }`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`Failed to fetch telemetry data: ${response.status}`);
      }

      const data = await response.json();
      console.log("Received telemetry data:", data); // Debug log
      setTelemetryData(data);
      setLastUpdate(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      console.error("Failed to fetch telemetry data:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchTelemetryData();

    // Set up interval for periodic updates
    const interval = setInterval(fetchTelemetryData, refreshInterval);

    return () => clearInterval(interval);
  }, [backendUrl, sessionId, refreshInterval]);

  const formatSpeed = (speed: number) => {
    return `${speed.toFixed(1)} m/s`;
  };

  const formatVoltage = (voltage: number) => {
    return `${voltage.toFixed(2)}V`;
  };

  const formatAngle = (angle: number) => {
    return `${((angle * 180) / Math.PI).toFixed(1)}°`;
  };

  const formatAngularSpeed = (speed: number) => {
    return `${((speed * 180) / Math.PI).toFixed(1)}°/s`;
  };

  if (error) {
    return (
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-red-600">
            <Activity className="h-5 w-5" />
            Telemetry Error
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-red-600">{error}</p>
          <button
            onClick={fetchTelemetryData}
            className="mt-2 px-3 py-1 bg-red-100 text-red-700 rounded text-sm hover:bg-red-200"
          >
            Retry
          </button>
        </CardContent>
      </Card>
    );
  }

  if (!telemetryData) {
    return (
      <Card className="h-full">
        <CardContent className="flex items-center justify-center h-48">
          <div className="text-center">
            <div className="animate-spin h-8 w-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-2" />
            <p className="text-sm text-muted-foreground">
              Loading telemetry data...
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Check if required data sections exist
  if (
    !telemetryData.gps ||
    !telemetryData.attitude ||
    !telemetryData.vfr_hud ||
    !telemetryData.battery ||
    !telemetryData.system
  ) {
    return (
      <Card className="h-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-yellow-600">
            <Activity className="h-5 w-5" />
            Incomplete Data
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-yellow-600">
            Telemetry data is incomplete. Some sections may be missing.
          </p>
          <div className="mt-2 text-xs text-muted-foreground">
            <p>Available sections:</p>
            <ul className="list-disc list-inside">
              {telemetryData.gps && <li>GPS</li>}
              {telemetryData.attitude && <li>Attitude</li>}
              {telemetryData.vfr_hud && <li>VFR HUD</li>}
              {telemetryData.battery && <li>Battery</li>}
              {telemetryData.system && <li>System</li>}
            </ul>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div>
      {/* Header with last update time */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
          Telemetry Data
        </h3>
      </div>

      {/* Telemetry panels with proper spacing */}
      <div className="space-y-4">
        {/* GPS Data */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Navigation className="h-5 w-5" />
              GPS (GPS_RAW_INT)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid grid-cols-2 gap-1 text-sm">
              <div>
                <span className="text-muted-foreground">Lat:</span>
                <span className="ml-0.5">
                  {telemetryData.gps.latitude.toFixed(6)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Lon:</span>
                <span className="ml-0.5">
                  {telemetryData.gps.longitude.toFixed(6)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Altitude:</span>
                <span className="ml-0.5">
                  {telemetryData.gps.altitude.toFixed(1)}m
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Speed:</span>
                <span className="ml-0.5">
                  {formatSpeed(telemetryData.gps.speed)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Heading:</span>
                <span className="ml-0.5">
                  {telemetryData.gps.heading.toFixed(1)}°
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Satellites:</span>
                <span className="ml-0.5">{telemetryData.gps.satellites}</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Attitude Data */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Attitude (ATTITUDE)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid grid-cols-2 gap-1 text-sm">
              <div>
                <span className="text-muted-foreground">Roll:</span>
                <span className="ml-0.5">
                  {formatAngle(telemetryData.attitude.roll)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Pitch:</span>
                <span className="ml-0.5">
                  {formatAngle(telemetryData.attitude.pitch)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Yaw:</span>
                <span className="ml-0.5">
                  {formatAngle(telemetryData.attitude.yaw)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Roll Speed:</span>
                <span className="ml-0.5">
                  {formatAngularSpeed(telemetryData.attitude.rollspeed)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Pitch Speed:</span>
                <span className="ml-0.5">
                  {formatAngularSpeed(telemetryData.attitude.pitchspeed)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Yaw Speed:</span>
                <span className="ml-0.5">
                  {formatAngularSpeed(telemetryData.attitude.yawspeed)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* VFR HUD Data */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Gauge className="h-5 w-5" />
              Flight Data (VFR_HUD)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid grid-cols-2 gap-1 text-sm">
              <div>
                <span className="text-muted-foreground">Airspeed:</span>
                <span className="ml-0.5">
                  {formatSpeed(telemetryData.vfr_hud.airspeed)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Groundspeed:</span>
                <span className="ml-0.5">
                  {formatSpeed(telemetryData.vfr_hud.groundspeed)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Heading:</span>
                <span className="ml-0.5">
                  {telemetryData.vfr_hud.heading.toFixed(1)}°
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Throttle:</span>
                <span className="ml-0.5">
                  {telemetryData.vfr_hud.throttle.toFixed(1)}%
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Altitude:</span>
                <span className="ml-0.5">
                  {telemetryData.vfr_hud.alt.toFixed(1)}m
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Climb:</span>
                <span className="ml-0.5">
                  {formatSpeed(telemetryData.vfr_hud.climb)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Battery Data */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Battery className="h-5 w-5" />
              Battery (BATTERY_STATUS)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid grid-cols-2 gap-1 text-sm">
              <div>
                <span className="text-muted-foreground">Voltage:</span>
                <span className="ml-0.5">
                  {formatVoltage(telemetryData.battery.voltage)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Current:</span>
                <span className="ml-0.5">
                  {telemetryData.battery.current.toFixed(2)}A
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Remaining:</span>
                <span className="ml-0.5">
                  {telemetryData.battery.remaining.toFixed(1)}%
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* System Status */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              System (SYS_STATUS)
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid grid-cols-2 gap-1 text-sm">
              <div>
                <span className="text-muted-foreground">Load:</span>
                <span className="ml-0.5">
                  {telemetryData.system.load.toFixed(1)}%
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Health:</span>
                <Badge
                  variant={
                    telemetryData.system.sensors_health ===
                    telemetryData.system.sensors_enabled
                      ? "default"
                      : "destructive"
                  }
                  className="text-xs"
                >
                  {telemetryData.system.sensors_health ===
                  telemetryData.system.sensors_enabled
                    ? "OK"
                    : "Issues"}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
