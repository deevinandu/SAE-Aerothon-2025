"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Battery,
  Satellite,
  Navigation,
  Compass,
  Upload,
  Route,
} from "lucide-react";
import Link from "next/link";
import { useCesium } from "@/context/CesiumContext";
import { parseKML, kmlToCesiumFormat } from "@/utils/kmlParser";
import { renderKMLData, renderPoint } from "@/utils/cesiumHelpers";
import {
  generateSurveillancePath,
  renderSurveillancePath,
  clearSurveillancePath,
} from "@/utils/pathGenerator";

export default function TelemetryOverlay({
  backendUrl = "http://localhost:8000",
}) {
  const [telemetry, setTelemetry] = useState(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [connectError, setConnectError] = useState("");
  const [protocol, setProtocol] = useState("UDP");
  const [serialPort, setSerialPort] = useState("");
  // Predefined common serial port options (platform-agnostic list)
  const commonSerialOptions = React.useMemo(() => {
    const win = Array.from({ length: 20 }, (_, i) => `COM${i + 1}`);
    const linux = [
      "/dev/ttyUSB0",
      "/dev/ttyUSB1",
      "/dev/ttyUSB2",
      "/dev/ttyUSB3",
      "/dev/ttyACM0",
      "/dev/ttyACM1",
      "/dev/ttyACM2",
      "/dev/ttyACM3",
    ];
    const mac = [
      "/dev/cu.usbserial-0001",
      "/dev/cu.usbserial",
      "/dev/cu.usbmodem-0001",
      "/dev/cu.usbmodem",
      "/dev/tty.usbserial-10",
    ];
    return [...win, ...linux, ...mac];
  }, []);
  const [baudRate, setBaudRate] = useState(57600);
  const [host, setHost] = useState("127.0.0.1");
  const [port, setPort] = useState(14550);

  // Multi-drone fleet support
  const [multiConnectionMode, setMultiConnectionMode] = useState(false);
  const [connections, setConnections] = useState([
    {
      id: 1,
      protocol: "UDP",
      host: "127.0.0.1",
      port: 14550,
      serialPort: "",
      baud: 57600,
    },
  ]);
  const [fleetStatus, setFleetStatus] = useState(null);
  const [selectedDroneId, setSelectedDroneId] = useState(null);
  const [uploadedKmlFile, setUploadedKmlFile] = useState(null);
  const [generatedPath, setGeneratedPath] = useState(null);
  const [isGeneratingPath, setIsGeneratingPath] = useState(false);
  const [isStartingMission, setIsStartingMission] = useState(false);
  const [missionStarted, setMissionStarted] = useState(false);
  const [missionAltitude, setMissionAltitude] = useState("");
  const [missionSpeed, setMissionSpeed] = useState("");
  const fileInputRef = useRef(null);
  const { viewer, kmlUploaded, setKmlUploaded, manualWaypointsCount } =
    useCesium();
  const droneEntityRef = useRef(null);
  const droneEntitiesRef = useRef({}); // Map of sys_id -> entity for multiple drones
  const kmlEntitiesRef = useRef([]);
  const hasZoomedToUavRef = useRef(false);

  // No browser enumeration; the dropdown provides common options only

  // Helper to validate numeric values
  const isFiniteNumber = (v) => typeof v === "number" && Number.isFinite(v);

  // Helper to add or update the UAV pin (single drone mode)
  const updateUavPin = (viewer, lon, lat) => {
    const Cesium = window.Cesium;
    if (!viewer || !Cesium || !isFiniteNumber(lat) || !isFiniteNumber(lon)) {
      return;
    }

    const position = Cesium.Cartesian3.fromDegrees(lon, lat, 0);

    if (droneEntityRef.current) {
      // Update existing pin
      droneEntityRef.current.position = position;
    } else {
      // Create new pin if it doesn't exist
      droneEntityRef.current = viewer.entities.add({
        name: "UAV",
        position: position,
        billboard: {
          image: "/drone-icon.png",
          width: 48,
          height: 48,
          rotation: Cesium.Math.toRadians(90),
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
    }
  };

  // Helper to update all drone pins (multi-drone mode)
  const updateFleetPins = (viewer, fleet) => {
    const Cesium = window.Cesium;
    if (!viewer || !Cesium || !fleet) return;

    const droneColors = [
      "#00FF00", // Green
      "#0080FF", // Blue
      "#FF8000", // Orange
      "#FF00FF", // Magenta
      "#FFFF00", // Yellow
      "#00FFFF", // Cyan
    ];

    Object.entries(fleet).forEach(([sysIdStr, droneData]) => {
      const sysId = parseInt(sysIdStr);
      const lat = droneData.latitude_deg;
      const lon = droneData.longitude_deg;

      if (!isFiniteNumber(lat) || !isFiniteNumber(lon)) return;

      const position = Cesium.Cartesian3.fromDegrees(lon, lat, 0);
      const color = droneColors[(sysId - 1) % droneColors.length];
      const isSelected = selectedDroneId === sysId;

      if (droneEntitiesRef.current[sysId]) {
        // Update existing pin
        droneEntitiesRef.current[sysId].position = position;
        if (droneEntitiesRef.current[sysId].billboard) {
          droneEntitiesRef.current[sysId].billboard.width = isSelected
            ? 56
            : 48;
          droneEntitiesRef.current[sysId].billboard.height = isSelected
            ? 56
            : 48;
        }
        if (droneEntitiesRef.current[sysId].label) {
          droneEntitiesRef.current[sysId].label.text = `Drone ${sysId}`;
          droneEntitiesRef.current[sysId].label.font = isSelected
            ? "bold 14px sans-serif"
            : "12px sans-serif";
        }
      } else {
        // Create new pin
        droneEntitiesRef.current[sysId] = viewer.entities.add({
          name: `Drone ${sysId}`,
          position: position,
          billboard: {
            image: "/drone-icon.png",
            width: isSelected ? 56 : 48,
            height: isSelected ? 56 : 48,
            rotation: Cesium.Math.toRadians(90),
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            color: Cesium.Color.fromCssColorString(color),
          },
          label: {
            text: `Drone ${sysId}`,
            font: isSelected ? "bold 14px sans-serif" : "12px sans-serif",
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -30),
          },
        });
      }
    });

    // Remove entities for drones that are no longer in the fleet
    Object.keys(droneEntitiesRef.current).forEach((sysIdStr) => {
      const sysId = parseInt(sysIdStr);
      if (!fleet[sysId]) {
        viewer.entities.remove(droneEntitiesRef.current[sysId]);
        delete droneEntitiesRef.current[sysId];
      }
    });
  };

  const handleFileSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith(".kml") && !file.name.endsWith(".kmz")) {
      alert("Please select a valid KML file");
      return;
    }

    try {
      const text = await file.text();
      const parsedKML = parseKML(text);
      const cesiumData = kmlToCesiumFormat(parsedKML);

      if (viewer) {
        // --- Start of Controlled Sequence ---

        // 1. Synchronously remove the existing pin
        if (droneEntityRef.current) {
          viewer.entities.remove(droneEntityRef.current);
          droneEntityRef.current = null;
        }

        // 2. Render KML without automatically zooming and hide placemarks
        const ents = renderKMLData(viewer, cesiumData, {
          clearExisting: false,
          zoomToBounds: false,
          polygonStyle: {
            strokeColor: "#FFD700",
            fillColor: "rgba(255, 255, 255, 0.1)",
            strokeWidth: 5,
            outline: true,
            outlineColor: "#FFD700",
          },
          lineStyle: { color: "#FFD700", width: 7 },
          pointStyle: { show: false }, // Explicitly hide points
          billboardStyle: { show: false }, // Explicitly hide icons
        });
        kmlEntitiesRef.current = ents || [];

        // 3. Calculate combined bounds and fly the camera
        const latRaw = telemetry?.gps?.latitude;
        const lonRaw = telemetry?.gps?.longitude;
        const lat = typeof latRaw === "string" ? Number(latRaw) : latRaw;
        const lon = typeof lonRaw === "string" ? Number(lonRaw) : lonRaw;

        const kmlBounds = cesiumData?.bounds;
        let west = kmlBounds?.west;
        let south = kmlBounds?.south;
        let east = kmlBounds?.east;
        let north = kmlBounds?.north;

        if (isFiniteNumber(lon) && isFiniteNumber(lat)) {
          west = west != null ? Math.min(west, lon) : lon;
          east = east != null ? Math.max(east, lon) : lon;
          south = south != null ? Math.min(south, lat) : lat;
          north = north != null ? Math.max(north, lat) : lat;
        }

        if (
          isFiniteNumber(west) &&
          isFiniteNumber(east) &&
          isFiniteNumber(south) &&
          isFiniteNumber(north)
        ) {
          const padW = (east - west || 0.001) * 0.1;
          const padH = (north - south || 0.001) * 0.1;
          const rect = window.Cesium.Rectangle.fromDegrees(
            west - padW,
            south - padH,
            east + padW,
            north + padH
          );

          viewer.camera.flyTo({
            destination: rect,
            duration: 1.5,
            complete: () => {
              // 4. Re-create the pin only after the flight is finished
              updateUavPin(viewer, lon, lat);
            },
          });
        } else {
          // If for some reason bounds are invalid, still re-add the pin
          updateUavPin(viewer, lon, lat);
        }
        // --- End of Controlled Sequence ---
      }

      setUploadedKmlFile(file);
      try {
        setKmlUploaded(true);
      } catch (_) {}
    } catch (error) {
      console.error("Error processing KML file:", error);
      // Make sure pin can reappear if something fails
      if (viewer && telemetry) {
        const lat = telemetry.gps.latitude;
        const lon = telemetry.gps.longitude;
        updateUavPin(viewer, lon, lat);
      }
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // ... (keep buildConnectionString, handleStartMission, handleGeneratePath)
  const buildConnectionString = () => {
    if (protocol === "SERIAL") {
      return serialPort || "";
    }
    const h = (host || "").trim();
    const p = String(port || "").trim();
    const proto = protocol === "TCP" ? "tcp" : "udp";
    return h && p ? `${proto}:${h}:${p}` : "";
  };

  const handleStartMission = async () => {
    if (!uploadedKmlFile) {
      alert("Please upload a KML file first");
      return;
    }

    const conn = buildConnectionString();
    if (!conn) {
      alert(
        "Please configure a valid connection first (UDP/TCP host:port or Serial port)"
      );
      return;
    }

    setIsStartingMission(true);
    let success = false;
    try {
      const form = new FormData();
      form.append("kml_file", uploadedKmlFile);
      form.append("use_drone_position", "true");
      // Provide manual fallback using current telemetry if available
      if (
        telemetry?.gps?.latitude != null &&
        telemetry?.gps?.longitude != null
      ) {
        form.append("start_lat", String(telemetry.gps.latitude));
        form.append("start_lon", String(telemetry.gps.longitude));
      }
      // Use default values if user left inputs empty
      const altitude = missionAltitude || 50;
      const speed = missionSpeed || 5;
      form.append("altitude", String(altitude));
      form.append("speed", String(speed));
      form.append("sensor_width", String(30));
      form.append("overlap", String(0.2));
      form.append("connection_string", conn);
      form.append("save_to_file", "false");
      form.append("auto_start", "true");
      form.append("end_action", "RTL");

      // Add sys_id if in multi-connection mode and a drone is selected
      if (multiConnectionMode && selectedDroneId) {
        form.append("sys_id", String(selectedDroneId));
      }

      const resp = await fetch(`${backendUrl}/mission/start`, {
        method: "POST",
        body: form,
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(
          data?.detail || data?.message || "Mission start failed"
        );
      }

      alert("Mission started successfully.");
      console.log("Mission start summary:", data?.summary);
      setMissionStarted(true); // Mark mission as started
      success = true;
    } catch (err) {
      console.error("Start mission error:", err);
      alert(`Failed to start mission: ${err?.message || err}`);
    } finally {
      if (!success) {
        setIsStartingMission(false); // Only reset loading state if failed
      }
    }
  };

  // Compute KML blocking state early for downstream hooks
  const isKmlBlocked = (manualWaypointsCount || 0) > 0;

  // Unified controls integration: listen for global events from left panel
  useEffect(() => {
    const onStartKml = () => {
      if (!isKmlBlocked && uploadedKmlFile) {
        handleStartMission();
      }
    };
    const onClearKml = () => {
      try {
        if (generatedPath && viewer) {
          clearSurveillancePath(viewer, generatedPath);
          setGeneratedPath(null);
        }
        // Remove KML geofence entities
        if (viewer && kmlEntitiesRef.current && kmlEntitiesRef.current.length) {
          kmlEntitiesRef.current.forEach((e) => {
            try {
              viewer.entities.remove(e);
            } catch (_) {}
          });
          kmlEntitiesRef.current = [];
        }
      } catch (_) {}
      setUploadedKmlFile(null);
      try {
        setKmlUploaded(false);
      } catch (_) {}
    };
    const onKmlAltitude = (ev) => {
      const alt = ev?.detail;
      setMissionAltitude(alt === undefined || alt === null ? "" : alt);
    };
    const onGeneratePath = () => {
      if (!isKmlBlocked && uploadedKmlFile && !isGeneratingPath) {
        handleGeneratePath();
      }
    };
    window.addEventListener("start-kml-mission", onStartKml);
    window.addEventListener("clear-kml", onClearKml);
    window.addEventListener("kml-altitude", onKmlAltitude);
    window.addEventListener("generate-kml-path", onGeneratePath);
    return () => {
      window.removeEventListener("start-kml-mission", onStartKml);
      window.removeEventListener("clear-kml", onClearKml);
      window.removeEventListener("kml-altitude", onKmlAltitude);
      window.removeEventListener("generate-kml-path", onGeneratePath);
    };
  }, [isKmlBlocked, uploadedKmlFile, viewer, generatedPath, isGeneratingPath]);

  const handleGeneratePath = async () => {
    if (!uploadedKmlFile) {
      alert("Please upload a KML file first");
      return;
    }

    if (!telemetry || !telemetry.gps) {
      alert("Waiting for GPS telemetry data...");
      return;
    }

    if (!viewer) {
      alert("Cesium viewer not ready");
      return;
    }

    setIsGeneratingPath(true);

    try {
      // Use current GPS position as UAV start position
      const uavStart = {
        latitude: telemetry.gps.latitude,
        longitude: telemetry.gps.longitude,
      };

      console.log("Generating path with UAV start:", uavStart);

      const result = await generateSurveillancePath(
        uploadedKmlFile,
        uavStart,
        30, // sensor width in meters
        0.2 // 20% overlap
      );

      console.log("Path generated:", result);

      // Clear previous path if exists
      if (generatedPath) {
        clearSurveillancePath(viewer, generatedPath);
      }

      // Render the new path
      const pathData = renderSurveillancePath(viewer, result.waypoints, {
        lineColor: "#00FF00",
        lineWidth: 3,
        pointColor: "#FFFF00",
        pointSize: 8,
        showWaypoints: true,
      });

      setGeneratedPath(pathData);

      console.log(
        `Path generated: ${result.statistics.total_waypoints} waypoints, ` +
          `${result.statistics.path_length_km} km, ` +
          `${(result.statistics.coverage_ratio * 100).toFixed(1)}% coverage`
      );
    } catch (error) {
      console.error("Error generating path:", error);
      alert(`Failed to generate path: ${error.message}`);
    } finally {
      setIsGeneratingPath(false);
    }
  };

  // Fetch fleet status when in multi-connection mode
  useEffect(() => {
    if (!isConnected || !multiConnectionMode) {
      setFleetStatus(null);
      return;
    }

    const fetchFleetStatus = async () => {
      try {
        const response = await fetch(`${backendUrl}/fleet/status`);
        if (response.ok) {
          const data = await response.json();
          setFleetStatus(data);

          // Auto-select first drone if none selected
          if (
            !selectedDroneId &&
            data.fleet &&
            Object.keys(data.fleet).length > 0
          ) {
            const firstSysId = parseInt(Object.keys(data.fleet)[0]);
            setSelectedDroneId(firstSysId);
            // Dispatch event for other components
            try {
              window.dispatchEvent(
                new CustomEvent("drone-selected", {
                  detail: { sysId: firstSysId },
                })
              );
            } catch (_) {}
          }
        }
      } catch (error) {
        console.error("Failed to fetch fleet status:", error);
      }
    };

    fetchFleetStatus();
    const interval = setInterval(fetchFleetStatus, 1000);

    return () => clearInterval(interval);
  }, [backendUrl, isConnected, multiConnectionMode, selectedDroneId]);

  // Update fleet pins when fleet status changes
  useEffect(() => {
    if (multiConnectionMode && viewer && fleetStatus && fleetStatus.fleet) {
      updateFleetPins(viewer, fleetStatus.fleet);

      // Auto-zoom to show all drones on first connection
      if (
        !hasZoomedToUavRef.current &&
        Object.keys(fleetStatus.fleet).length > 0
      ) {
        const drones = Object.values(fleetStatus.fleet);
        const validDrones = drones.filter(
          (d) =>
            d &&
            isFiniteNumber(d.latitude_deg) &&
            isFiniteNumber(d.longitude_deg) &&
            d.latitude_deg !== 0 && // Filter out invalid coordinates
            d.longitude_deg !== 0
        );

        if (validDrones.length > 0) {
          // Calculate bounds to include all drones
          let west = Infinity,
            east = -Infinity,
            south = Infinity,
            north = -Infinity;
          let maxAlt = 0;

          validDrones.forEach((drone) => {
            const lat = drone.latitude_deg;
            const lon = drone.longitude_deg;
            const alt = drone.altitude_m || 0;

            west = Math.min(west, lon);
            east = Math.max(east, lon);
            south = Math.min(south, lat);
            north = Math.max(north, lat);
            maxAlt = Math.max(maxAlt, alt);
          });

          // Ensure we have valid bounds
          if (
            isFiniteNumber(west) &&
            isFiniteNumber(east) &&
            isFiniteNumber(south) &&
            isFiniteNumber(north) &&
            west !== Infinity &&
            east !== -Infinity
          ) {
            // If we have multiple drones, use rectangle view
            if (validDrones.length > 1) {
              // Add padding (15% on each side for better view)
              const padLon = Math.max((east - west) * 0.15, 0.001);
              const padLat = Math.max((north - south) * 0.15, 0.001);

              const rect = window.Cesium.Rectangle.fromDegrees(
                west - padLon,
                south - padLat,
                east + padLon,
                north + padLat
              );

              viewer.camera.flyTo({
                destination: rect,
                duration: 1.5,
              });
            } else {
              // Single drone - fly to its position with good altitude
              const firstDrone = validDrones[0];
              viewer.camera.flyTo({
                destination: window.Cesium.Cartesian3.fromDegrees(
                  firstDrone.longitude_deg,
                  firstDrone.latitude_deg,
                  Math.max(maxAlt, 0) + 1000 // Higher altitude to see area better
                ),
                duration: 1.5,
              });
            }

            hasZoomedToUavRef.current = true;
            console.log(
              "[TelemetryOverlay] Camera positioned to show",
              validDrones.length,
              "drone(s)"
            );
          }
        }
      }
    }
  }, [viewer, fleetStatus, multiConnectionMode, selectedDroneId]);

  // Fetch telemetry for selected drone
  useEffect(() => {
    if (!isConnected) {
      setTelemetry(null);
      if (viewer) {
        if (droneEntityRef.current) {
          viewer.entities.remove(droneEntityRef.current);
          droneEntityRef.current = null;
        }
        // Clear all drone entities
        Object.values(droneEntitiesRef.current).forEach((entity) => {
          viewer.entities.remove(entity);
        });
        droneEntitiesRef.current = {};
      }
      return;
    }

    // In multi-connection mode, skip telemetry fetch here (handled by fleet status)
    if (multiConnectionMode && !selectedDroneId) {
      setTelemetry(null);
      return;
    }

    const fetchTelemetry = async () => {
      try {
        let url = `${backendUrl}/telemetry/sensors`;
        if (multiConnectionMode && selectedDroneId) {
          url += `?sys_id=${selectedDroneId}`;
        }
        console.log(
          "[TelemetryOverlay] Fetching telemetry from:",
          url,
          "selectedDroneId:",
          selectedDroneId
        );
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          console.log("[TelemetryOverlay] Received telemetry data:", data);
          setTelemetry(data);
        } else {
          console.error(
            "[TelemetryOverlay] Failed to fetch telemetry:",
            response.status,
            response.statusText
          );
        }
      } catch (error) {
        console.error("[TelemetryOverlay] Error fetching telemetry:", error);
      }
    };

    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 1000);

    return () => clearInterval(interval);
  }, [backendUrl, isConnected, viewer, multiConnectionMode, selectedDroneId]);

  // This effect handles the UAV pin based on telemetry (single drone mode only)
  useEffect(() => {
    if (multiConnectionMode) return; // Skip in multi-drone mode (handled by fleet status)

    const latRaw = telemetry?.gps?.latitude;
    const lonRaw = telemetry?.gps?.longitude;
    const lat = typeof latRaw === "string" ? Number(latRaw) : latRaw;
    const lon = typeof lonRaw === "string" ? Number(lonRaw) : lonRaw;

    if (viewer && isFiniteNumber(lat) && isFiniteNumber(lon)) {
      updateUavPin(viewer, lon, lat);
    }

    // Auto-zoom on first valid telemetry after connection
    if (
      viewer &&
      !uploadedKmlFile &&
      !hasZoomedToUavRef.current &&
      isFiniteNumber(lat) &&
      isFiniteNumber(lon)
    ) {
      const altRaw = telemetry?.vfr_hud?.alt ?? telemetry?.gps?.altitude ?? 0;
      const alt = typeof altRaw === "string" ? Number(altRaw) : altRaw;

      viewer.camera.flyTo({
        destination: window.Cesium.Cartesian3.fromDegrees(
          lon,
          lat,
          Math.max(alt, 0) + 700
        ),
        duration: 1.5,
      });
      hasZoomedToUavRef.current = true;
    }
  }, [telemetry, viewer, uploadedKmlFile, multiConnectionMode]);

  const battery = telemetry?.battery?.remaining || 0;
  const satellites = telemetry?.gps?.satellites || 0;
  const speed = telemetry?.vfr_hud?.groundspeed || 0;
  const heading = telemetry?.vfr_hud?.heading || 0;
  const altitude = telemetry?.vfr_hud?.alt || 0;

  const getBatteryColor = (level) => {
    if (level > 50) return "text-green-400";
    if (level > 20) return "text-yellow-400";
    return "text-red-400";
  };

  const armedStatus = telemetry?.status?.armed;
  const modeStatus = telemetry?.status?.mode;

  const handleConnect = async () => {
    setIsConnecting(true);
    setConnectError("");
    try {
      let body;

      if (multiConnectionMode) {
        // Multi-connection mode: send array of connections
        body = {
          connections: connections.map((conn) => {
            if (conn.protocol === "SERIAL") {
              return {
                protocol: "SERIAL",
                port: conn.serialPort,
                baud: Number(conn.baud),
              };
            } else {
              return {
                protocol: conn.protocol,
                host: conn.host,
                port: Number(conn.port),
              };
            }
          }),
        };
      } else {
        // Single connection mode (backward compatible)
        body = { protocol };
        if (protocol === "SERIAL") {
          body.port = serialPort;
          body.baud = Number(baudRate);
        } else {
          body.host = host;
          body.port = Number(port);
        }
      }

      const resp = await fetch(`${backendUrl}/telemetry/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to connect");
      }
      setIsConnected(true);
      try {
        window.dispatchEvent(new Event("telemetry-connected"));
      } catch (_) {}
      hasZoomedToUavRef.current = false;
      setSelectedDroneId(null); // Reset selection on reconnect
    } catch (e) {
      console.error("Connect error:", e);
      setConnectError(e.message || "Failed to connect");
      setIsConnected(false);
    } finally {
      setIsConnecting(false);
    }
  };

  const addConnection = () => {
    const newId = Math.max(...connections.map((c) => c.id), 0) + 1;
    setConnections([
      ...connections,
      {
        id: newId,
        protocol: "UDP",
        host: "127.0.0.1",
        port: 14550 + connections.length,
        serialPort: "",
        baud: 57600,
      },
    ]);
  };

  const removeConnection = (id) => {
    if (connections.length > 1) {
      setConnections(connections.filter((c) => c.id !== id));
    }
  };

  const updateConnection = (id, field, value) => {
    setConnections(
      connections.map((c) => (c.id === id ? { ...c, [field]: value } : c))
    );
  };

  const handleDisconnect = async () => {
    setIsConnecting(true);
    setConnectError("");
    try {
      const resp = await fetch(`${backendUrl}/telemetry/disconnect`, {
        method: "POST",
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to disconnect");
      }
      setIsConnected(false);
      hasZoomedToUavRef.current = false; // Reset zoom flag for next connection
      try {
        window.dispatchEvent(new Event("telemetry-disconnected"));
      } catch (_) {}
    } catch (e) {
      console.error("Disconnect error:", e);
      setConnectError(e.message || "Failed to disconnect");
    } finally {
      setIsConnecting(false);
    }
  };

  return (
    <div className="absolute inset-x-0 top-0 text-white">
      {/* Top connection bar */}
      <div className="w-full bg-black/70 backdrop-blur-md border-b border-gray-700/50 shadow">
        {/* Main connection controls */}
        <div className="flex items-center gap-3 px-4 py-2 flex-wrap">
          <span className="text-sm font-semibold text-gray-200">
            Connection
          </span>

          {/* Multi-connection mode toggle */}
          <label className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={multiConnectionMode}
              onChange={(e) => {
                setMultiConnectionMode(e.target.checked);
                if (!e.target.checked) {
                  setSelectedDroneId(null);
                  setFleetStatus(null);
                }
              }}
              disabled={isConnected}
              className="w-4 h-4"
            />
            <span>Multi-Drone Mode</span>
          </label>

          {!multiConnectionMode ? (
            <>
              {/* Single connection mode */}
              <select
                value={protocol}
                onChange={(e) => setProtocol(e.target.value)}
                className="text-xs bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-gray-200 focus:outline-none"
              >
                <option value="UDP">UDP</option>
                <option value="TCP">TCP</option>
                <option value="SERIAL">Serial</option>
              </select>

              {protocol === "SERIAL" ? (
                <div className="flex items-center gap-2">
                  <select
                    value={serialPort}
                    onChange={(e) => setSerialPort(e.target.value)}
                    className="text-xs bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-gray-200 focus:outline-none"
                  >
                    <option value="">Select COM/Serial port</option>
                    {commonSerialOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={baudRate}
                    onChange={(e) => setBaudRate(e.target.value)}
                    placeholder="57600"
                    className="text-xs w-24 bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-gray-200 placeholder-gray-400 focus:outline-none"
                  />
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <input
                    value={host}
                    onChange={(e) => setHost(e.target.value)}
                    placeholder="Host (e.g. 127.0.0.1)"
                    className="text-xs w-40 bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-gray-200 placeholder-gray-400 focus:outline-none"
                  />
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    value={port}
                    onChange={(e) => setPort(e.target.value)}
                    placeholder="Port (e.g. 14550)"
                    className="text-xs w-28 bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-gray-200 placeholder-gray-400 focus:outline-none"
                  />
                </div>
              )}
            </>
          ) : (
            <>
              {/* Multi-connection mode */}
              <div className="flex items-center gap-2 flex-wrap">
                {connections.map((conn) => (
                  <div
                    key={conn.id}
                    className="flex items-center gap-1 border border-gray-600 rounded px-2 py-1"
                  >
                    <select
                      value={conn.protocol}
                      onChange={(e) =>
                        updateConnection(conn.id, "protocol", e.target.value)
                      }
                      disabled={isConnected}
                      className="text-xs bg-white/5 border border-gray-600 rounded px-1 py-0.5 text-gray-200 focus:outline-none"
                    >
                      <option value="UDP">UDP</option>
                      <option value="TCP">TCP</option>
                      <option value="SERIAL">Serial</option>
                    </select>
                    {conn.protocol === "SERIAL" ? (
                      <>
                        <select
                          value={conn.serialPort}
                          onChange={(e) =>
                            updateConnection(
                              conn.id,
                              "serialPort",
                              e.target.value
                            )
                          }
                          disabled={isConnected}
                          className="text-xs bg-white/5 border border-gray-600 rounded px-1 py-0.5 text-gray-200 focus:outline-none w-32"
                        >
                          <option value="">Port</option>
                          {commonSerialOptions.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                        <input
                          type="text"
                          inputMode="numeric"
                          value={conn.baud}
                          onChange={(e) =>
                            updateConnection(conn.id, "baud", e.target.value)
                          }
                          disabled={isConnected}
                          placeholder="57600"
                          className="text-xs w-20 bg-white/5 border border-gray-600 rounded px-1 py-0.5 text-gray-200 placeholder-gray-400 focus:outline-none"
                        />
                      </>
                    ) : (
                      <>
                        <input
                          value={conn.host}
                          onChange={(e) =>
                            updateConnection(conn.id, "host", e.target.value)
                          }
                          disabled={isConnected}
                          placeholder="Host"
                          className="text-xs w-32 bg-white/5 border border-gray-600 rounded px-1 py-0.5 text-gray-200 placeholder-gray-400 focus:outline-none"
                        />
                        <input
                          type="text"
                          inputMode="numeric"
                          value={conn.port}
                          onChange={(e) =>
                            updateConnection(conn.id, "port", e.target.value)
                          }
                          disabled={isConnected}
                          placeholder="Port"
                          className="text-xs w-20 bg-white/5 border border-gray-600 rounded px-1 py-0.5 text-gray-200 placeholder-gray-400 focus:outline-none"
                        />
                      </>
                    )}
                    {!isConnected && connections.length > 1 && (
                      <button
                        onClick={() => removeConnection(conn.id)}
                        className="text-red-400 hover:text-red-300 text-xs px-1"
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
                {!isConnected && (
                  <button
                    onClick={addConnection}
                    className="text-xs border border-gray-600 rounded px-2 py-1 text-gray-300 hover:bg-white/5"
                  >
                    + Add
                  </button>
                )}
              </div>
            </>
          )}

          {/* Drone selector (only in multi-connection mode when connected) */}
          {multiConnectionMode &&
            isConnected &&
            fleetStatus &&
            fleetStatus.fleet && (
              <>
                <span className="text-xs text-gray-300 font-semibold">
                  Drone:
                </span>
                <select
                  value={selectedDroneId || ""}
                  onChange={(e) => {
                    const newSysId = e.target.value
                      ? parseInt(e.target.value)
                      : null;
                    console.log(
                      "[TelemetryOverlay] Drone selection changed to:",
                      newSysId
                    );
                    setSelectedDroneId(newSysId);
                    // Dispatch event for other components (like MissionPlannerPanel)
                    try {
                      window.dispatchEvent(
                        new CustomEvent("drone-selected", {
                          detail: { sysId: newSysId },
                        })
                      );
                      console.log(
                        "[TelemetryOverlay] Dispatched drone-selected event for sysId:",
                        newSysId
                      );
                    } catch (e) {
                      console.error(
                        "[TelemetryOverlay] Error dispatching event:",
                        e
                      );
                    }
                  }}
                  className="text-xs bg-white/10 border border-gray-500 rounded-md px-3 py-1 text-gray-200 focus:outline-none focus:border-blue-400 min-w-[140px]"
                >
                  <option value="">Select Drone</option>
                  {Object.entries(fleetStatus.fleet).map(
                    ([sysId, droneData]) => (
                      <option key={sysId} value={sysId}>
                        Drone {sysId} ({droneData.flight_mode || "UNKNOWN"})
                      </option>
                    )
                  )}
                </select>
              </>
            )}

          {/* Fleet status indicator */}
          {multiConnectionMode && isConnected && fleetStatus && (
            <span className="text-xs text-gray-300">
              {fleetStatus.count || 0} drone{fleetStatus.count !== 1 ? "s" : ""}{" "}
              connected
            </span>
          )}

          {/* Status */}
          <span
            className={`ml-auto text-xs ${
              isConnected
                ? "text-green-400"
                : connectError
                ? "text-red-400"
                : "text-gray-400"
            }`}
          >
            {isConnected
              ? "Connected"
              : connectError
              ? connectError
              : "Not connected"}
          </span>

          {/* Connect/Disconnect */}
          {!isConnected ? (
            <button
              onClick={handleConnect}
              disabled={isConnecting}
              className={`text-xs border rounded-md px-3 py-1 cursor-pointer ${
                isConnecting
                  ? "bg-gray-600/20 border-gray-500/30 text-gray-400 cursor-not-allowed"
                  : "bg-green-600/20 hover:bg-green-600/30 border-green-500/30 text-green-300"
              }`}
            >
              {isConnecting ? "Connecting..." : "Connect"}
            </button>
          ) : (
            <button
              onClick={handleDisconnect}
              disabled={isConnecting}
              className={`text-xs border rounded-md px-3 py-1 cursor-pointer ${
                isConnecting
                  ? "bg-gray-600/20 border-gray-500/30 text-gray-400 cursor-not-allowed"
                  : "bg-red-600/20 hover:bg-red-600/30 border-red-500/30 text-red-300"
              }`}
            >
              {isConnecting ? "Disconnecting..." : "Disconnect"}
            </button>
          )}
        </div>
      </div>

      {/* Hidden KML file input (controlled from MissionPlannerPanel) */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".kml,.kmz"
        onChange={handleFileSelect}
        className="hidden"
      />
    </div>
  );
}
