"use client";

import React, { useEffect, useRef } from "react";
import Script from "next/script";
import { useCesium } from "@/context/CesiumContext";

export default function CesiumGlobe() {
  const cesiumContainer = useRef(null);
  const viewerRef = useRef(null);
  const { registerViewer } = useCesium();

  useEffect(() => {
    // Initialize Cesium viewer once the script is loaded
    const initCesium = () => {
      if (window.Cesium && cesiumContainer.current && !viewerRef.current) {
        // Set Cesium Ion access token from environment variable
        const token = process.env.NEXT_PUBLIC_CESIUM_ION_ACCESS_TOKEN;
        if (token) {
          window.Cesium.Ion.defaultAccessToken = token;
        }

        viewerRef.current = new window.Cesium.Viewer(cesiumContainer.current, {
          timeline: false,
          animation: false,
          baseLayerPicker: false,
          fullscreenButton: false,
          geocoder: false,
          homeButton: false,
          navigationHelpButton: false,
          sceneModePicker: false,
          selectionIndicator: false,
          infoBox: false,
          creditContainer: document.createElement("div"), // Hide credits
        });

        // Register viewer with context
        registerViewer(viewerRef.current);
      }
    };

    // Check if Cesium is already loaded
    if (window.Cesium) {
      initCesium();
    }

    return () => {
      if (viewerRef.current) {
        viewerRef.current.destroy();
        viewerRef.current = null;
      }
    };
  }, [registerViewer]);

  const handleScriptLoad = () => {
    if (window.Cesium && cesiumContainer.current && !viewerRef.current) {
      // Set Cesium Ion access token from environment variable
      const token = process.env.NEXT_PUBLIC_CESIUM_ION_ACCESS_TOKEN;
      if (token) {
        window.Cesium.Ion.defaultAccessToken = token;
      }

      viewerRef.current = new window.Cesium.Viewer(cesiumContainer.current, {
        timeline: false,
        animation: false,
        baseLayerPicker: false,
        fullscreenButton: false,
        geocoder: false,
        homeButton: false,
        navigationHelpButton: false,
        sceneModePicker: false,
        selectionIndicator: false,
        infoBox: false,
        creditContainer: document.createElement("div"), // Hide credits
      });

      // Register viewer with context
      registerViewer(viewerRef.current);
    }
  };

  return (
    <>
      <Script
        src="https://cesium.com/downloads/cesiumjs/releases/1.108/Build/Cesium/Cesium.js"
        strategy="afterInteractive"
        onLoad={handleScriptLoad}
      />
      <link
        rel="stylesheet"
        href="https://cesium.com/downloads/cesiumjs/releases/1.108/Build/Cesium/Widgets/widgets.css"
      />
      <div ref={cesiumContainer} className="w-full h-full" />
    </>
  );
}
