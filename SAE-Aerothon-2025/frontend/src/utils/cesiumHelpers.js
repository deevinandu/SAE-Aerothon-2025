export function renderPolygon(viewer, polygon, options = {}) {
  if (!window.Cesium || !viewer) return null;

  const Cesium = window.Cesium;

  // Convert positions to Cartesian3
  const positions = polygon.positions.map((pos) =>
    Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, pos.height || 0)
  );

  // Add polygon entity
  const entity = viewer.entities.add({
    name: polygon.name || "Polygon",
    polygon: {
      hierarchy: new Cesium.PolygonHierarchy(positions),
      material: Cesium.Color.fromCssColorString(
        options.fillColor || "#ffffff"
      ).withAlpha(0.25),
      outline: true,
      outlineColor: Cesium.Color.fromCssColorString(
        options.strokeColor || "#2dc0fb"
      ),
      outlineWidth: options.strokeWidth || 3,
      height: 0,
      extrudedHeight: options.extrudedHeight || 0,
    },
  });

  // Add a separate border polyline to control border thickness (polygon outline width is limited)
  const closedPositions =
    positions.length > 0 ? [...positions, positions[0]] : positions;
  const borderEntity = viewer.entities.add({
    name: (polygon.name || "Polygon") + " Border",
    polyline: {
      positions: closedPositions,
      width: options.borderWidth || options.strokeWidth || 3,
      material: Cesium.Color.fromCssColorString(
        options.strokeColor || "#2dc0fb"
      ),
      clampToGround: options.clampToGround !== false,
    },
  });

  // Return both entities so callers can track and remove both
  return [entity, borderEntity];
}

export function renderLineString(viewer, line, options = {}) {
  if (!window.Cesium || !viewer) return null;

  const Cesium = window.Cesium;

  // Convert positions to Cartesian3
  const positions = line.positions.map((pos) =>
    Cesium.Cartesian3.fromDegrees(pos.longitude, pos.latitude, pos.height || 0)
  );

  // Add polyline entity
  const entity = viewer.entities.add({
    name: line.name || "Line",
    polyline: {
      positions: positions,
      width: options.width || 3,
      material: Cesium.Color.fromCssColorString(options.color || "#2dc0fb"),
      clampToGround: options.clampToGround !== false,
    },
  });

  return entity;
}

/**
 * Render point on Cesium viewer
 * @param {Object} viewer - Cesium viewer instance
 * @param {Object} point - Point data {name, position: {longitude, latitude, height}}
 * @param {Object} options - Styling options
 */
export function renderPoint(viewer, point, options = {}) {
  if (!window.Cesium || !viewer) return null;

  const Cesium = window.Cesium;

  const position = Cesium.Cartesian3.fromDegrees(
    point.position.longitude,
    point.position.latitude,
    point.position.height || 0
  );

  const entity = viewer.entities.add({
    name: point.name || "Point",
    position: position,
    point: {
      pixelSize: options.pixelSize || 10,
      color: Cesium.Color.fromCssColorString(options.color || "#2dc0fb"),
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 2,
    },
    label:
      options.showLabel !== false
        ? {
            text: point.name,
            font: "14px sans-serif",
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            pixelOffset: new Cesium.Cartesian2(0, -20),
          }
        : undefined,
  });

  return entity;
}

export function zoomToBounds(viewer, bounds, options = {}) {
  if (!window.Cesium || !viewer || !bounds) return;

  const Cesium = window.Cesium;

  // Apply a small padding so the view isn't cut-to-cut
  const paddingRatio =
    typeof options.paddingRatio === "number" ? options.paddingRatio : 0.1; // 10% padding
  const width = Math.max(1e-9, bounds.east - bounds.west);
  const height = Math.max(1e-9, bounds.north - bounds.south);
  const padW = width * paddingRatio;
  const padH = height * paddingRatio;

  const west = bounds.west - padW;
  const south = bounds.south - padH;
  const east = bounds.east + padW;
  const north = bounds.north + padH;

  const rectangle = Cesium.Rectangle.fromDegrees(west, south, east, north);

  viewer.camera.flyTo({
    destination: rectangle,
    duration: options.duration || 2,
    offset: new Cesium.HeadingPitchRange(
      options.heading || 0,
      Cesium.Math.toRadians(options.pitch || -45),
      options.range || 7000 // slightly farther default range for a more relaxed view
    ),
  });
}

export function clearKMLEntities(viewer) {
  if (!viewer) return;
  viewer.entities.removeAll();
}

export function renderKMLData(viewer, data, options = {}) {
  const {
    clearExisting = true,
    zoomToBounds = true,
    pointStyle = {},
    lineStyle = {},
    polygonStyle = {},
    billboardStyle = { show: false }, // Add this to hide icons/billboards
  } = options;

  if (clearExisting) {
    viewer.entities.removeAll();
  }

  const entities = [];

  // Suppress points and billboards if style.show is false
  if (pointStyle?.show !== false) {
    (data.points || []).forEach((point) => {
      const entity = renderPoint(viewer, point, pointStyle);
      if (entity) entities.push(entity);
    });
  }

  (data.lines || []).forEach((line) => {
    const entity = renderLineString(viewer, line, lineStyle);
    if (entity) entities.push(entity);
  });

  (data.polygons || []).forEach((polygon) => {
    const result = renderPolygon(viewer, polygon, polygonStyle);
    if (Array.isArray(result)) {
      result.forEach((e) => e && entities.push(e));
    } else if (result) {
      entities.push(result);
    }
  });

  // Apply billboard style (specifically to hide them)
  (data.billboards || []).forEach((bb) => {
    const entity = viewer.entities.add({
      position: bb.position,
      billboard: {
        image: bb.image,
        ...billboardStyle,
      },
      name: bb.name,
    });
    entities.push(entity);
  });

  if (zoomToBounds && entities.length > 0) {
    viewer.flyTo(entities, { duration: 1.5 });
  }

  return entities;
}
