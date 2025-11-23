"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { useCesium } from "@/context/CesiumContext";

const DEFAULT_ALTITUDE_M = 5;
const DEFAULT_CAMERA_HEIGHT_M = 1200;

const MODES = ["HOLD", "WAYPOINT", "LOITER", "TAKEOFF", "LAND"];

export default function MissionPlannerPanel({
  backendUrl = "http://localhost:8000",
}) {
  const { viewer, kmlUploaded, setManualWaypointsCount } = useCesium();

  const [addMode, setAddMode] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(null);
  const [latInput, setLatInput] = useState(0);
  const [lonInput, setLonInput] = useState(0);
  const [cameraHeight, setCameraHeight] = useState(DEFAULT_CAMERA_HEIGHT_M);
  const [waypoints, setWaypoints] = useState([]);
  const [missionStatus, setMissionStatus] = useState("");

  // Telemetry-local state (merged panel top section)
  const [telemetry, setTelemetry] = useState(null);

  // Planner mode switcher
  const [plannerMode, setPlannerMode] = useState("MANUAL"); // or "KML"
  const [kmlAltitude, setKmlAltitude] = useState("");

  // Cesium references
  const handlerRef = useRef(null);
  const entitiesRef = useRef({
    points: [],
    polyline: null,
    yellowSegments: [],
  });
  const dragStateRef = useRef({ dragging: false, idx: null });
  const telemetryFetchControllerRef = useRef(null);

  const Cesium = typeof window !== "undefined" ? window.Cesium : null;

  const polylinePositions = useMemo(() => {
    if (!Cesium) return [];
    return waypoints.map((wp) =>
      Cesium.Cartesian3.fromDegrees(wp.longitude, wp.latitude, 0)
    );
  }, [Cesium, waypoints]);

  // Helpers
  const toDegrees = (cartesian) => {
    if (!Cesium || !cartesian) return null;
    const carto = Cesium.Ellipsoid.WGS84.cartesianToCartographic(cartesian);
    if (!carto) return null;
    return {
      longitude: Cesium.Math.toDegrees(carto.longitude),
      latitude: Cesium.Math.toDegrees(carto.latitude),
      altitude: carto.height || 0,
    };
  };

  const addWaypointAt = (lng, lat, alt = DEFAULT_ALTITUDE_M) => {
    setWaypoints((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        longitude: lng,
        latitude: lat,
        altitude: alt,
        mode: "WAYPOINT",
      },
    ]);
  };

  const updateWaypoint = (idx, patch) => {
    setWaypoints((prev) =>
      prev.map((wp, i) => (i === idx ? { ...wp, ...patch } : wp))
    );
  };

  const removeWaypoint = (idx) => {
    setWaypoints((prev) => prev.filter((_, i) => i !== idx));
    if (selectedIdx === idx) setSelectedIdx(null);
  };

  const clearWaypoints = () => {
    setWaypoints([]);
    setSelectedIdx(null);
  };

  // Fly to lat/lon
  const handleFlyTo = () => {
    if (!viewer || !Cesium) return;
    const dest = Cesium.Cartesian3.fromDegrees(
      Number(lonInput),
      Number(latInput),
      Number(cameraHeight) || DEFAULT_CAMERA_HEIGHT_M
    );
    viewer.camera.flyTo({ destination: dest, duration: 1.2 });
  };

  // Telemetry fetch (merged in this panel) - only fetch when connected
  const [hasActiveConnection, setHasActiveConnection] = useState(false);
  const [selectedDroneId, setSelectedDroneId] = useState(null);

  useEffect(() => {
    let interval = null;
    let mounted = true;
    const connectedRef = { current: false };
    const fetchControllerRef = telemetryFetchControllerRef;

    // Listen for drone selection changes from TelemetryOverlay
    const handleDroneSelection = (event) => {
      if (!mounted) return;
      console.log(
        "[MissionPlannerPanel] Drone selection event received:",
        event.detail
      );
      const newSysId = event.detail?.sysId || null;
      setSelectedDroneId(newSysId);
      console.log(
        "[MissionPlannerPanel] Updated selectedDroneId to:",
        newSysId
      );
    };

    window.addEventListener("drone-selected", handleDroneSelection);
    console.log("[MissionPlannerPanel] Listening for drone-selected events");

    // Also listen for telemetry-connected to auto-select first drone
    const handleConnected = () => {
      if (!mounted) {
        console.log(
          "[MissionPlannerPanel] handleConnected called but not mounted"
        );
        return;
      }
      console.log(
        "[MissionPlannerPanel] handleConnected - fetching fleet status for auto-select"
      );
      // Fetch fleet status to auto-select first drone
      fetch(`${backendUrl}/fleet/status`)
        .then((r) => r.json())
        .then((data) => {
          if (
            data.fleet &&
            Object.keys(data.fleet).length > 0 &&
            !selectedDroneId
          ) {
            const firstSysId = parseInt(Object.keys(data.fleet)[0]);
            console.log(
              "[MissionPlannerPanel] Auto-selecting first drone:",
              firstSysId
            );
            setSelectedDroneId(firstSysId);
            window.dispatchEvent(
              new CustomEvent("drone-selected", {
                detail: { sysId: firstSysId },
              })
            );
          }
        })
        .catch((e) =>
          console.error("[MissionPlannerPanel] Error fetching fleet status:", e)
        );
    };

    window.addEventListener("telemetry-connected", handleConnected);

    const startPolling = () => {
      if (interval) {
        console.log("[MissionPlannerPanel] Polling already started, skipping");
        return;
      }
      console.log("[MissionPlannerPanel] Starting telemetry polling...");
      interval = setInterval(async () => {
        if (!connectedRef.current || !mounted) {
          console.log(
            "[MissionPlannerPanel] Skipping fetch - connectedRef:",
            connectedRef.current,
            "mounted:",
            mounted
          );
          return;
        }
        try {
          const nextController = new AbortController();
          fetchControllerRef.current = nextController;
          let url = `${backendUrl}/telemetry/sensors`;
          // If a drone is selected, fetch that specific drone's data
          if (selectedDroneId) {
            url += `?sys_id=${selectedDroneId}`;
          }
          console.log(
            "[MissionPlannerPanel] Fetching telemetry from:",
            url,
            "selectedDroneId:",
            selectedDroneId
          );
          const resp = await fetch(url, {
            signal: nextController.signal,
          });
          if (!mounted || !connectedRef.current) return;
          if (resp.ok) {
            const data = await resp.json();
            console.log("[MissionPlannerPanel] Received telemetry data:", data);
            // Skip if it's a fleet snapshot (shouldn't happen with sys_id, but just in case)
            if (!data.fleet) {
              console.log(
                "[MissionPlannerPanel] Setting telemetry. GPS:",
                data.gps,
                "Battery:",
                data.battery,
                "Status:",
                data.status
              );
              setTelemetry(data);
            } else {
              console.warn(
                "[MissionPlannerPanel] Received fleet snapshot instead of single drone data"
              );
            }
          } else {
            console.error(
              "[MissionPlannerPanel] Failed to fetch telemetry:",
              resp.status,
              resp.statusText
            );
          }
        } catch (err) {
          console.error(
            "[MissionPlannerPanel] Exception fetching telemetry:",
            err
          );
        }
      }, 1000);
    };

    const stopPolling = () => {
      if (interval) {
        clearInterval(interval);
        interval = null;
      }
      const controller = fetchControllerRef.current;
      if (controller) {
        controller.onabort = null;
        try {
          controller.abort();
        } catch (err) {
          console.debug(
            "[MissionPlannerPanel] Error aborting fetch controller in cleanup:",
            err
          );
        }
        fetchControllerRef.current = null;
      }
    };

    const onConnected = () => {
      if (!mounted) {
        console.log("[MissionPlannerPanel] onConnected called but not mounted");
        return;
      }
      console.log("[MissionPlannerPanel] onConnected - starting polling");
      connectedRef.current = true;
      setHasActiveConnection(true);
      startPolling();
    };
    const onDisconnected = () => {
      if (!mounted) return;
      connectedRef.current = false;
      setHasActiveConnection(false);
      setTelemetry(null);
      stopPolling();
    };

    window.addEventListener("telemetry-connected", onConnected);
    window.addEventListener("telemetry-disconnected", onDisconnected);

    console.log(
      "[MissionPlannerPanel] Registered telemetry-connected/disconnected listeners"
    );

    // Ensure we start disconnected
    onDisconnected();

    // Check if already connected (in case component mounts after connection)
    // This handles the case where TelemetryOverlay connects before MissionPlannerPanel mounts
    const checkExistingConnection = async () => {
      try {
        const response = await fetch(`${backendUrl}/fleet/status`);
        if (response.ok) {
          const data = await response.json();
          if (data.count > 0) {
            console.log(
              "[MissionPlannerPanel] Found existing connection, starting polling"
            );
            onConnected();
          }
        }
      } catch (e) {
        // Ignore errors, connection might not be active
      }
    };
    checkExistingConnection();

    return () => {
      mounted = false;
      stopPolling();
      window.removeEventListener("telemetry-connected", onConnected);
      window.removeEventListener("telemetry-disconnected", onDisconnected);
      window.removeEventListener("drone-selected", handleDroneSelection);
      window.removeEventListener("telemetry-connected", handleConnected);
    };
  }, [backendUrl, selectedDroneId]);

  // Create/refresh Cesium entities when waypoints change
  useEffect(() => {
    if (!viewer || !Cesium) return;
    try {
      setManualWaypointsCount(waypoints.length);
    } catch (_) {}

    // Ensure polyline exists with dynamic positions
    if (!entitiesRef.current.polyline) {
      const dynamicPositions = new Cesium.CallbackProperty(() => {
        return waypoints.map((wp) =>
          Cesium.Cartesian3.fromDegrees(wp.longitude, wp.latitude, 0)
        );
      }, false);

      entitiesRef.current.polyline = viewer.entities.add({
        name: "Mission Path",
        polyline: {
          positions: dynamicPositions,
          width: 3,
          material: Cesium.Color.fromCssColorString("#00FF88"),
          clampToGround: true,
        },
      });
    }

    // Create/update yellow segments for each consecutive waypoint pair
    const syncYellowSegments = () => {
      const segs = entitiesRef.current.yellowSegments;
      const needed = Math.max(0, waypoints.length - 1);
      while (segs.length > needed) {
        const ent = segs.pop();
        viewer.entities.remove(ent);
      }
      while (segs.length < needed) {
        const ent = viewer.entities.add({
          name: `Segment-${segs.length}`,
          polyline: {
            positions: [],
            width: 4,
            material: Cesium.Color.fromCssColorString("#FFD700"),
            clampToGround: true,
          },
        });
        segs.push(ent);
      }
      for (let i = 0; i < needed; i++) {
        const a = waypoints[i];
        const b = waypoints[i + 1];
        segs[i].polyline.positions = [
          Cesium.Cartesian3.fromDegrees(a.longitude, a.latitude, 0),
          Cesium.Cartesian3.fromDegrees(b.longitude, b.latitude, 0),
        ];
      }
    };
    syncYellowSegments();

    // Sync point entities to waypoint list length
    const points = entitiesRef.current.points;
    while (points.length > waypoints.length) {
      const ent = points.pop();
      viewer.entities.remove(ent);
    }
    while (points.length < waypoints.length) {
      const newIdx = points.length;
      const labelText = `${newIdx + 1}`;
      const ent = viewer.entities.add({
        name: `WP-${newIdx + 1}`,
        position: Cesium.Cartesian3.fromDegrees(
          waypoints[newIdx].longitude,
          waypoints[newIdx].latitude,
          0
        ),
        point: {
          pixelSize: 10,
          color: Cesium.Color.fromCssColorString("#2dc0fb"),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        label: {
          text: labelText,
          font: "14px sans-serif",
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -20),
        },
      });
      points.push(ent);
    }
    points.forEach((ent, i) => {
      const wp = waypoints[i];
      ent.position = Cesium.Cartesian3.fromDegrees(
        wp.longitude,
        wp.latitude,
        0
      );
      if (ent.point) {
        ent.point.heightReference = Cesium.HeightReference.CLAMP_TO_GROUND;
      }
      if (ent.label) {
        const abbrev =
          wp.mode === "WAYPOINT" ? "WP" : wp.mode.substring(0, 2).toUpperCase();
        ent.label.text = `${i + 1} ${abbrev}`;
      }
    });

    return () => {};
  }, [viewer, Cesium, waypoints, setManualWaypointsCount]);

  // Handle interactions: add by click, drag to move
  useEffect(() => {
    if (!viewer || !Cesium) return;

    if (!handlerRef.current) {
      handlerRef.current = new Cesium.ScreenSpaceEventHandler(
        viewer.scene.canvas
      );
    }
    const handler = handlerRef.current;

    // Add waypoint on left click when addMode is enabled
    const leftClickFn = (click) => {
      if (!addMode || plannerMode !== "MANUAL") return;
      const pos = viewer.camera.pickEllipsoid(
        click.position,
        Cesium.Ellipsoid.WGS84
      );
      if (!pos) return;
      const deg = toDegrees(pos);
      if (!deg) return;
      addWaypointAt(deg.longitude, deg.latitude, DEFAULT_ALTITUDE_M);
    };

    // Select or start drag on left down when not in add mode
    const leftDownFn = (click) => {
      if (addMode || plannerMode !== "MANUAL") return;
      const picked = viewer.scene.pick(click.position);
      const points = entitiesRef.current.points;
      if (picked && picked.id) {
        const idx = points.findIndex((e) => e === picked.id);
        if (idx !== -1) {
          setSelectedIdx(idx);
          dragStateRef.current = { dragging: true, idx };
          viewer.scene.screenSpaceCameraController.enableRotate = false;
        }
      }
    };

    const mouseMoveFn = (movement) => {
      if (!dragStateRef.current.dragging || plannerMode !== "MANUAL") return;
      const idx = dragStateRef.current.idx;
      if (idx == null) return;
      const cart = viewer.camera.pickEllipsoid(
        movement.endPosition,
        Cesium.Ellipsoid.WGS84
      );
      if (!cart) return;
      const deg = toDegrees(cart);
      if (!deg) return;
      updateWaypoint(idx, { longitude: deg.longitude, latitude: deg.latitude });
    };

    const leftUpFn = () => {
      if (dragStateRef.current.dragging) {
        dragStateRef.current = { dragging: false, idx: null };
        viewer.scene.screenSpaceCameraController.enableRotate = true;
      }
    };

    handler.setInputAction(leftClickFn, Cesium.ScreenSpaceEventType.LEFT_CLICK);
    handler.setInputAction(leftDownFn, Cesium.ScreenSpaceEventType.LEFT_DOWN);
    handler.setInputAction(mouseMoveFn, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
    handler.setInputAction(leftUpFn, Cesium.ScreenSpaceEventType.LEFT_UP);

    return () => {
      if (handler) {
        handler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_CLICK);
        handler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOWN);
        handler.removeInputAction(Cesium.ScreenSpaceEventType.MOUSE_MOVE);
        handler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_UP);
      }
    };
  }, [viewer, Cesium, addMode, plannerMode]);

  // Cleanup entities when unmounting
  useEffect(() => {
    return () => {
      if (viewer && entitiesRef.current) {
        if (entitiesRef.current.polyline)
          viewer.entities.remove(entitiesRef.current.polyline);
        if (
          entitiesRef.current.yellowSegments &&
          entitiesRef.current.yellowSegments.length
        ) {
          entitiesRef.current.yellowSegments.forEach((e) =>
            viewer.entities.remove(e)
          );
        }
        entitiesRef.current.points.forEach((e) => viewer.entities.remove(e));
        entitiesRef.current = {
          points: [],
          polyline: null,
          yellowSegments: [],
        };
      }
      if (handlerRef.current) {
        handlerRef.current.destroy();
        handlerRef.current = null;
      }
    };
  }, [viewer]);

  const selected = selectedIdx != null ? waypoints[selectedIdx] : null;

  const handleStartMission = async () => {
    if (!waypoints.length) {
      alert("Add at least one waypoint");
      return;
    }
    try {
      setMissionStatus("Uploading mission...");

      // Build request body - include sys_id if a drone is selected (multi-drone mode)
      const requestBody = {
        waypoints,
        speed: 5,
        end_action: "RTL",
      };

      // If a drone is selected, include sys_id for multi-drone support
      if (selectedDroneId) {
        requestBody.sys_id = selectedDroneId;
        console.log(
          `[MissionPlannerPanel] Uploading mission to drone sys_id=${selectedDroneId}`
        );
      }

      const resp = await fetch(`${backendUrl}/mission/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to start manual mission");
      }
      const data = await resp.json().catch(() => ({}));
      const started = data?.summary?.auto_started ? " and started" : "";
      setMissionStatus(`Manual mission uploaded${started}.`);
      alert("Manual mission uploaded.");
    } catch (e) {
      const msg = e?.message || String(e);
      setMissionStatus(msg);
      alert(msg);
    }
  };

  // Unified Start/Clear actions
  const handleUnifiedStart = () => {
    if (plannerMode === "KML") {
      window.dispatchEvent(new Event("start-kml-mission"));
    } else {
      handleStartMission();
    }
  };

  const handleUnifiedClear = () => {
    if (plannerMode === "KML") {
      window.dispatchEvent(new Event("clear-kml"));
    } else {
      clearWaypoints();
    }
  };

  const canStart =
    (plannerMode === "MANUAL" && waypoints.length > 0) ||
    (plannerMode === "KML" && kmlUploaded);
  const canClear = canStart;

  // Extract telemetry values with proper null/undefined handling
  const battery = telemetry?.battery?.remaining ?? 0;
  const satellites = telemetry?.gps?.satellites ?? 0;
  const speed = telemetry?.vfr_hud?.groundspeed ?? telemetry?.gps?.speed ?? 0;
  const heading = telemetry?.vfr_hud?.heading ?? telemetry?.gps?.heading ?? 0;
  const altitude = telemetry?.vfr_hud?.alt ?? telemetry?.gps?.altitude ?? 0;
  const armedStatus = telemetry?.status?.armed;
  const modeStatus = telemetry?.status?.mode;

  // Debug: Log extracted values
  if (telemetry) {
    console.log("[MissionPlannerPanel] Extracted values:", {
      battery,
      satellites,
      speed,
      heading,
      altitude,
      armedStatus,
      modeStatus,
      "telemetry.battery": telemetry.battery,
      "telemetry.gps": telemetry.gps,
      "telemetry.vfr_hud": telemetry.vfr_hud,
      "telemetry.status": telemetry.status,
    });
  }

  // Debug logging
  useEffect(() => {
    if (telemetry) {
      console.log("[MissionPlannerPanel] Current telemetry state:", {
        battery,
        satellites,
        speed,
        heading,
        altitude,
        armedStatus,
        modeStatus,
        fullTelemetry: telemetry,
      });
    } else {
      console.log("[MissionPlannerPanel] No telemetry data available");
    }
  }, [
    telemetry,
    battery,
    satellites,
    speed,
    heading,
    altitude,
    armedStatus,
    modeStatus,
  ]);

  const getBatteryColor = (level) => {
    if (level > 50) return "text-green-400";
    if (level > 20) return "text-yellow-400";
    return "text-red-400";
  };

  // Fetch fleet status to show drone selector in multi-drone mode
  const [fleetStatus, setFleetStatus] = useState(null);

  useEffect(() => {
    if (!hasActiveConnection) {
      setFleetStatus(null);
      return;
    }

    const fetchFleetStatus = async () => {
      try {
        const response = await fetch(`${backendUrl}/fleet/status`);
        if (response.ok) {
          const data = await response.json();
          setFleetStatus(data);
        }
      } catch (error) {
        console.error(
          "[MissionPlannerPanel] Failed to fetch fleet status:",
          error
        );
      }
    };

    fetchFleetStatus();
    const interval = setInterval(fetchFleetStatus, 2000); // Poll every 2 seconds
    return () => clearInterval(interval);
  }, [backendUrl, hasActiveConnection]);

  return (
    <div className="absolute top-16 left-4 text-white w-[320px]">
      <div className="bg-black/70 backdrop-blur-md rounded-lg border border-gray-700/50 shadow-2xl p-4 space-y-3">
        {/* Drone selector in multi-drone mode */}
        {fleetStatus &&
          fleetStatus.fleet &&
          Object.keys(fleetStatus.fleet).length > 1 && (
            <div className="border-b border-gray-700/50 pb-2">
              <label className="text-xs text-gray-400 mb-1 block">
                Select Drone
              </label>
              <select
                value={selectedDroneId || ""}
                onChange={(e) => {
                  const newSysId = e.target.value
                    ? parseInt(e.target.value)
                    : null;
                  setSelectedDroneId(newSysId);
                  // Dispatch event to sync with TelemetryOverlay
                  try {
                    window.dispatchEvent(
                      new CustomEvent("drone-selected", {
                        detail: { sysId: newSysId },
                      })
                    );
                  } catch (_) {}
                }}
                className="w-full text-xs bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-gray-200 focus:outline-none"
              >
                <option value="">All Drones (First)</option>
                {Object.entries(fleetStatus.fleet).map(([sysId, droneData]) => (
                  <option key={sysId} value={sysId}>
                    Drone {sysId}
                  </option>
                ))}
              </select>
              {selectedDroneId && (
                <div className="text-xs text-gray-400 mt-1">
                  Showing: Drone {selectedDroneId}
                </div>
              )}
            </div>
          )}

        {/* Telemetry summary (top section) */}
        <div className="border-b border-gray-700/50 pb-3 space-y-2">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${
                  armedStatus ? "bg-green-400" : "bg-yellow-400"
                }`}
              ></span>
              <span className="text-xs text-gray-300">Battery</span>
            </div>
            <span className={`text-sm font-mono ${getBatteryColor(battery)}`}>
              {typeof battery === "number" ? battery.toFixed(1) : battery}%
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-gray-300">
            <div>
              Satellites:{" "}
              <span className="font-mono text-blue-400">{satellites}</span>
            </div>
            <div>
              Speed:{" "}
              <span className="font-mono text-cyan-400">
                {typeof speed === "number" ? speed.toFixed(1) : speed} m/s
              </span>
            </div>
            <div>
              Heading:{" "}
              <span className="font-mono text-purple-400">
                {typeof heading === "number" ? heading.toFixed(0) : heading}°
              </span>
            </div>
            <div>
              Altitude:{" "}
              <span className="font-mono text-orange-400">
                {typeof altitude === "number" ? altitude.toFixed(1) : altitude}{" "}
                m
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={`px-2 py-0.5 rounded text-[10px] border ${
                armedStatus === true
                  ? "bg-green-500/20 text-green-400 border-green-500/30"
                  : armedStatus === false
                  ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                  : "bg-gray-600/30 text-gray-300 border-gray-500/30"
              }`}
            >
              {armedStatus === true
                ? "ARMED"
                : armedStatus === false
                ? "DISARMED"
                : "--"}
            </span>
            <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 text-[10px] rounded border border-blue-500/30">
              {modeStatus ?? "--"}
            </span>
          </div>
        </div>

        {/* Mode switcher */}
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setPlannerMode("MANUAL")}
            className={`flex-1 rounded-md px-2 py-1 border ${
              plannerMode === "MANUAL"
                ? "bg-blue-600/60 border-blue-500/40 text-blue-200"
                : "bg-white/5 border-gray-600 text-gray-300"
            }`}
          >
            Manual
          </button>
          <button
            onClick={() => setPlannerMode("KML")}
            className={`flex-1 rounded-md px-2 py-1 border ${
              plannerMode === "KML"
                ? "bg-blue-600/60 border-blue-500/40 text-blue-200"
                : "bg-white/5 border-gray-600 text-gray-300"
            }`}
          >
            KML
          </button>
        </div>

        {plannerMode === "MANUAL" ? (
          <>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-200">
                Mission Planner
              </span>
              <button
                onClick={() => setAddMode((v) => !v)}
                className={`text-xs rounded-md px-2 py-1 border cursor-pointer ${
                  addMode
                    ? "bg-green-600/60 border-green-500/40 text-green-200"
                    : "bg-white/5 border-gray-600 text-gray-300 hover:bg-blue-600/30 hover:border-blue-500/40 hover:text-blue-200"
                }`}
              >
                {addMode ? "Adding: Click to place" : "Add Waypoints"}
              </button>
            </div>

            {/* Fly-to controls removed as requested */}

            {/* Waypoint list */}
            <div className="max-h-64 overflow-y-auto space-y-2 border-t border-gray-700/50 pt-3">
              {waypoints.length === 0 ? (
                <div className="text-xs text-gray-400">
                  No waypoints. Enable "Add Waypoints" and click on the map.
                </div>
              ) : (
                waypoints.map((wp, i) => (
                  <div
                    key={wp.id}
                    className={`p-2 rounded-md border ${
                      selectedIdx === i
                        ? "bg-white/10 border-blue-500/40"
                        : "bg-white/5 border-gray-600"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-xs text-gray-200 font-semibold">
                        {i + 1}. {wp.mode}
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => setSelectedIdx(i)}
                          className="text-xs rounded px-2 py-0.5 bg-blue-600/20 border border-blue-500/30 text-blue-200"
                        >
                          Select
                        </button>
                        <button
                          onClick={() => removeWaypoint(i)}
                          className="text-xs rounded px-2 py-0.5 bg-red-600/20 border border-red-500/30 text-red-200"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 mt-2">
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] text-gray-300">Lat</span>
                        <div className="w-full bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-xs text-gray-300 select-text">
                          {wp.latitude.toFixed
                            ? wp.latitude.toFixed(6)
                            : wp.latitude}
                        </div>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] text-gray-300">Lon</span>
                        <div className="w-full bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-xs text-gray-300 select-text">
                          {wp.longitude.toFixed
                            ? wp.longitude.toFixed(6)
                            : wp.longitude}
                        </div>
                      </div>
                      <div className="flex flex-col gap-1">
                        <span className="text-[10px] text-gray-300">
                          Alt (m)
                        </span>
                        <input
                          value={wp.altitude}
                          onChange={(e) =>
                            updateWaypoint(i, {
                              altitude: Number(e.target.value) || 0,
                            })
                          }
                          placeholder={`ex: ${DEFAULT_ALTITUDE_M}`}
                          aria-label={`Waypoint ${i + 1} altitude meters`}
                          className="w-full bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-xs placeholder-gray-400 focus:outline-none"
                        />
                      </div>
                      <div className="col-span-3 flex flex-col gap-1">
                        <span className="text-[10px] text-gray-300">Mode</span>
                        <select
                          value={wp.mode}
                          onChange={(e) =>
                            updateWaypoint(i, { mode: e.target.value })
                          }
                          aria-label={`Waypoint ${i + 1} mode`}
                          className="w-full bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-xs text-gray-200 focus:outline-none"
                        >
                          {MODES.map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        ) : (
          <>
            {/* KML Upload section */}
            <div className="space-y-2">
              <button
                onClick={() => {
                  // Open the hidden file input in TelemetryOverlay via DOM ref isn't possible; rely on click event
                  const input = document.querySelector(
                    'input[type="file"][accept=".kml,.kmz"]'
                  );
                  if (input) input.click();
                }}
                className="w-full bg-blue-600/20 hover:bg-blue-600/30 border border-blue-500/30 rounded-lg p-2 transition-colors text-center"
              >
                {kmlUploaded ? "Change KML" : "Upload KML"}
              </button>
              <div className="flex flex-col gap-1">
                <span className="text-xs text-gray-300">Altitude (m)</span>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9.]*"
                  value={kmlAltitude}
                  onChange={(e) => {
                    const val = e.target.value;
                    setKmlAltitude(val === "" ? "" : Number(val) || "");
                    window.dispatchEvent(
                      new CustomEvent("kml-altitude", {
                        detail: val === "" ? "" : Number(val) || "",
                      })
                    );
                  }}
                  placeholder="example: 50"
                  className="w-full bg-white/5 border border-gray-600 rounded-md px-2 py-1 text-sm placeholder-gray-400 focus:outline-none"
                />
              </div>
              <button
                onClick={() =>
                  window.dispatchEvent(new Event("generate-kml-path"))
                }
                disabled={!kmlUploaded}
                className={`w-full border rounded-lg p-2 transition-colors text-center cursor-pointer disabled:cursor-not-allowed ${
                  kmlUploaded
                    ? "bg-green-600/20 hover:bg-green-600/30 border-green-500/30 text-green-300"
                    : "bg-gray-600/20 border-gray-500/30 text-gray-400"
                }`}
              >
                Generate Path
              </button>
              <div className="text-[11px] text-gray-400">
                Tip: After choosing a KML, set altitude and press Start Mission.
              </div>
            </div>
          </>
        )}

        {/* Unified controls */}
        <div className="flex gap-2 pt-2">
          <button
            onClick={handleUnifiedClear}
            disabled={!canClear}
            className={`flex-1 border rounded-lg p-2 transition-colors text-center cursor-pointer disabled:cursor-not-allowed ${
              canClear
                ? "bg-white/5 border-gray-600 text-gray-300 hover:bg-red-600/20 hover:border-red-500/30 hover:text-red-200"
                : "bg-gray-600/20 border-gray-500/30 text-gray-400"
            }`}
          >
            Clear
          </button>
          <button
            onClick={handleUnifiedStart}
            disabled={!canStart}
            className={`flex-1 border rounded-lg p-2 transition-colors text-center cursor-pointer disabled:cursor-not-allowed ${
              canStart
                ? "bg-emerald-600/20 hover:bg-emerald-600/30 border-emerald-500/30 text-emerald-300"
                : "bg-gray-600/20 border-gray-500/30 text-gray-400"
            }`}
          >
            Start Mission
          </button>
        </div>
        {missionStatus && (
          <div className="text-[11px] text-gray-300 pt-1">{missionStatus}</div>
        )}
      </div>
    </div>
  );
}
