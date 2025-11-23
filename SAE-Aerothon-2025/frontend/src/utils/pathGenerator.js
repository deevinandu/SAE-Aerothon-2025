export async function generateSurveillancePath(
  kmlFile,
  uavStartPosition,
  sensorWidth = 30,
  overlap = 0.2
) {
  try {
    const formData = new FormData();
    formData.append("kml_file", kmlFile);
    formData.append("uav_start_lat", uavStartPosition.latitude.toString());
    formData.append("uav_start_lon", uavStartPosition.longitude.toString());
    formData.append("sensor_width", sensorWidth.toString());
    formData.append("overlap", overlap.toString());

    const response = await fetch("http://localhost:8000/path/generate", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || "Failed to generate path");
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error generating surveillance path:", error);
    throw error;
  }
}

export function renderSurveillancePath(viewer, waypoints, style = {}) {
  if (!viewer || !waypoints || waypoints.length < 2) return null;

  const defaultStyle = {
    lineColor: "#00FF00", // Green for path
    lineWidth: 7,
    pointColor: "#FFFF00", // Yellow for waypoints
    pointSize: 8,
    showWaypoints: true,
  };

  const finalStyle = { ...defaultStyle, ...style };

  // Convert waypoints to Cesium Cartesian3 positions
  const positions = waypoints.map((wp) =>
    window.Cesium.Cartesian3.fromDegrees(
      wp.longitude,
      wp.latitude,
      wp.altitude || 0
    )
  );

  // Add the path line
  const pathEntity = viewer.entities.add({
    name: "Surveillance Path",
    polyline: {
      positions: positions,
      width: finalStyle.lineWidth,
      material: window.Cesium.Color.fromCssColorString(finalStyle.lineColor),
      clampToGround: true,
    },
  });

  // Add waypoint markers if enabled
  const waypointEntities = [];
  if (finalStyle.showWaypoints) {
    waypoints.forEach((wp, index) => {
      const waypointEntity = viewer.entities.add({
        name: `Waypoint ${index + 1}`,
        position: window.Cesium.Cartesian3.fromDegrees(
          wp.longitude,
          wp.latitude,
          wp.altitude || 0
        ),
        point: {
          pixelSize: finalStyle.pointSize,
          color: window.Cesium.Color.fromCssColorString(finalStyle.pointColor),
          outlineColor: window.Cesium.Color.BLACK,
          outlineWidth: 2,
        },
        label: {
          text: `${index + 1}`,
          font: "12px sans-serif",
          fillColor: window.Cesium.Color.WHITE,
          outlineColor: window.Cesium.Color.BLACK,
          outlineWidth: 2,
          style: window.Cesium.LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: window.Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new window.Cesium.Cartesian2(0, -12),
          show: index === 0 || index === waypoints.length - 1, // Show only start and end labels
        },
      });
      waypointEntities.push(waypointEntity);
    });
  }

  // Start marker removed - using drone icon instead

  return {
    pathEntity,
    waypointEntities,
    startMarker: null, // No longer creating start marker since drone icon shows position
    waypoints,
  };
}

export function clearSurveillancePath(viewer, pathData) {
  if (!viewer || !pathData) return;

  if (pathData.pathEntity) {
    viewer.entities.remove(pathData.pathEntity);
  }

  if (pathData.waypointEntities) {
    pathData.waypointEntities.forEach((entity) => {
      viewer.entities.remove(entity);
    });
  }

  if (pathData.startMarker) {
    if (pathData.startMarker.circleEntity)
      viewer.entities.remove(pathData.startMarker.circleEntity);
    if (pathData.startMarker.arrowEntity)
      viewer.entities.remove(pathData.startMarker.arrowEntity);
  }
}
