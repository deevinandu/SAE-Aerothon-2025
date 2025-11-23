export function parseKML(kmlString) {
  const parser = new DOMParser();
  const xmlDoc = parser.parseFromString(kmlString, "text/xml");

  // Check for parsing errors
  const parserError = xmlDoc.querySelector("parsererror");
  if (parserError) {
    throw new Error("Failed to parse KML file");
  }

  const data = {
    name: "",
    description: "",
    placemarks: [],
    polygons: [],
    lineStrings: [],
    points: [],
    bounds: null,
  };

  // Get document name
  const docName = xmlDoc.querySelector("Document > name");
  if (docName) {
    data.name = docName.textContent;
  }

  // Parse all Placemarks
  const placemarks = xmlDoc.querySelectorAll("Placemark");

  placemarks.forEach((placemark) => {
    const name = placemark.querySelector("name")?.textContent || "Unnamed";
    const description =
      placemark.querySelector("description")?.textContent || "";

    // Parse Polygon
    const polygon = placemark.querySelector("Polygon");
    if (polygon) {
      const coordinates = parseCoordinates(
        polygon.querySelector("outerBoundaryIs coordinates")?.textContent || ""
      );
      data.polygons.push({
        name,
        description,
        coordinates,
      });
    }

    // Parse LineString
    const lineString = placemark.querySelector("LineString");
    if (lineString) {
      const coordinates = parseCoordinates(
        lineString.querySelector("coordinates")?.textContent || ""
      );
      data.lineStrings.push({
        name,
        description,
        coordinates,
      });
    }

    // Parse Point
    const point = placemark.querySelector("Point");
    if (point) {
      const coordinates = parseCoordinates(
        point.querySelector("coordinates")?.textContent || ""
      );
      if (coordinates.length > 0) {
        data.points.push({
          name,
          description,
          coordinate: coordinates[0],
        });
      }
    }

    data.placemarks.push({
      name,
      description,
    });
  });

  // Calculate bounds from all coordinates
  data.bounds = calculateBounds([
    ...data.polygons.flatMap((p) => p.coordinates),
    ...data.lineStrings.flatMap((l) => l.coordinates),
    ...data.points.map((p) => p.coordinate),
  ]);

  return data;
}

function parseCoordinates(coordString) {
  if (!coordString) return [];

  // Handle both space and newline separated coordinates
  return coordString
    .trim()
    .split(/[\s\n]+/)
    .filter((coord) => coord.trim().length > 0)
    .map((coord) => {
      const parts = coord.split(",").map(parseFloat);
      return parts.filter((n) => !isNaN(n));
    })
    .filter((coord) => coord.length >= 2);
}

function calculateBounds(coordinates) {
  if (coordinates.length === 0) return null;

  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;

  coordinates.forEach(([lon, lat]) => {
    west = Math.min(west, lon);
    south = Math.min(south, lat);
    east = Math.max(east, lon);
    north = Math.max(north, lat);
  });

  return { west, south, east, north };
}

export function kmlToCesiumFormat(kmlData) {
  return {
    polygons: kmlData.polygons.map((polygon) => ({
      name: polygon.name,
      description: polygon.description,
      positions: polygon.coordinates.map(([lon, lat, alt = 0]) => ({
        longitude: lon,
        latitude: lat,
        height: alt,
      })),
    })),
    lines: kmlData.lineStrings.map((line) => ({
      name: line.name,
      description: line.description,
      positions: line.coordinates.map(([lon, lat, alt = 0]) => ({
        longitude: lon,
        latitude: lat,
        height: alt,
      })),
    })),
    points: kmlData.points.map((point) => ({
      name: point.name,
      description: point.description,
      position: {
        longitude: point.coordinate[0],
        latitude: point.coordinate[1],
        height: point.coordinate[2] || 0,
      },
    })),
    bounds: kmlData.bounds,
  };
}
