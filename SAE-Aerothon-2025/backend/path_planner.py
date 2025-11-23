import xml.etree.ElementTree as ET
from shapely.geometry import Polygon, Point, LineString
from shapely import affinity
import numpy as np
import matplotlib.pyplot as plt

def load_kml_boundary(kml_file_path):
    """
    Parses a KML file to extract the geofence coordinates.
    """
    tree = ET.parse(kml_file_path)
    root = tree.getroot()
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    coordinates_str = ""
    for placemark in root.findall('.//kml:Placemark', ns):
        if placemark.find('.//kml:Polygon', ns) is not None:
            for polygon in placemark.findall('.//kml:Polygon', ns):
                for outer_boundary in polygon.findall('.//kml:outerBoundaryIs', ns):
                    for linear_ring in outer_boundary.findall('.//kml:LinearRing', ns):
                        coordinates_tag = linear_ring.find('.//kml:coordinates', ns)
                        if coordinates_tag is not None:
                            coordinates_str = coordinates_tag.text.strip()
                            break
                    if coordinates_str: break
                if coordinates_str: break
        if coordinates_str: break
    
    if not coordinates_str:
        raise ValueError("Could not find polygon coordinates in KML file.")

    geofence_coords = []
    for coord_pair in coordinates_str.split():
        parts = coord_pair.split(',')
        if len(parts) >= 2:
            lon, lat = map(float, parts[:2])
            geofence_coords.append((lon, lat))
        
    return geofence_coords

def find_entry_corner(geofence_polygon, uav_start_position):
    """
    Finds the closest corner of the geofence to the UAV's starting position.
    """
    corners = list(geofence_polygon.exterior.coords)
    closest_corner = min(corners, key=lambda corner: uav_start_position.distance(Point(corner)))
    return Point(closest_corner)

def shorten_segment(segment, distance):
    """
    Shortens a LineString segment from both ends by a specified distance.
    If the segment is too short to be shortened, it returns the original segment
    to ensure small corner-clipping passes are not discarded.
    """
    length = segment.length
    if length <= 2 * distance:
        return segment # Keep the original short segment
    
    start_point = segment.interpolate(distance)
    end_point = segment.interpolate(length - distance)
    
    return LineString([start_point, end_point])


def generate_surveillance_path(geofence_polygon, overlap, sensor_footprint_width, entry_point, verbose=False, force_short_axis=False):
    """
    Generates a truly optimized lawnmower path by first ensuring full coverage,
    then shortening each path segment for maximum efficiency without discarding
    critical corner-covering segments.
    """
    # 1. Find the Minimum Rotated Rectangle (MBR) and its properties
    mbr = geofence_polygon.minimum_rotated_rectangle
    mbr_coords = list(mbr.exterior.coords)

    edge1_len = Point(mbr_coords[0]).distance(Point(mbr_coords[1]))
    edge2_len = Point(mbr_coords[1]).distance(Point(mbr_coords[2]))

    # Determine sweep direction based on the longer edge, unless forced otherwise
    if (edge1_len > edge2_len and not force_short_axis) or \
       (edge1_len <= edge2_len and force_short_axis):
        long_edge_p1, long_edge_p2 = mbr_coords[0], mbr_coords[1]
    else:
        long_edge_p1, long_edge_p2 = mbr_coords[1], mbr_coords[2]

    angle_rad = np.arctan2(long_edge_p2[1] - long_edge_p1[1], long_edge_p2[0] - long_edge_p1[0])
    angle_deg = np.degrees(angle_rad)

    # 2. Rotate everything to be axis-aligned for simple calculation
    rotation_origin = geofence_polygon.centroid
    rotated_polygon = affinity.rotate(geofence_polygon, -angle_deg, origin=rotation_origin, use_radians=False)
    rotated_mbr = affinity.rotate(mbr, -angle_deg, origin=rotation_origin, use_radians=False)
    rotated_entry_point = affinity.rotate(entry_point, -angle_deg, origin=rotation_origin, use_radians=False)

    # 3. Calculate distances in degrees
    lat_mid = geofence_polygon.centroid.y
    meters_per_degree_lat = 111320.0
    step_over_deg = (sensor_footprint_width * (1 - overlap)) / meters_per_degree_lat
    inset_dist_deg_lat = (sensor_footprint_width / 2.0) / meters_per_degree_lat

    if verbose:
        print("\n--- Detailed Path Generation Log ---")
        print(f"  Input Overlap: {overlap:.4f}")
        print(f"  Sensor Width: {sensor_footprint_width}m")
        print(f"  Calculated Step-Over (deg): {step_over_deg:.8f}")
        print(f"  Calculated Inset Distance (deg): {inset_dist_deg_lat:.8f}")

    # 4. STAGE 1: Generate full-coverage scan lines over the entire MBR
    bounds = rotated_mbr.bounds
    min_x, min_y, max_x, max_y = bounds
    
    scan_y_coords_base = list(np.arange(min_y + inset_dist_deg_lat, max_y - inset_dist_deg_lat, step_over_deg))
    
    # Dynamic adjustment to consume leftover space
    if scan_y_coords_base:
        last_y = scan_y_coords_base[-1]
        remaining_gap = (max_y - inset_dist_deg_lat) - last_y
        if remaining_gap > 1e-7 and len(scan_y_coords_base) > 1:
            adjustment_per_step = remaining_gap / (len(scan_y_coords_base) - 1)
            
            if verbose:
                print(f"  Dynamic Spacing Triggered:")
                print(f"    - Base scan lines: {len(scan_y_coords_base)}")
                print(f"    - Remaining gap to fill: {remaining_gap:.8f} deg")
                print(f"    - Distributed adjustment per step: {adjustment_per_step:.8f} deg")

            new_scan_y = [scan_y_coords_base[0]]
            for i in range(1, len(scan_y_coords_base)):
                new_y = new_scan_y[i-1] + step_over_deg + adjustment_per_step
                new_scan_y.append(new_y)
            scan_y_coords = new_scan_y
        else:
            if verbose:
                print(f"  Dynamic Spacing NOT Triggered (gap too small or not enough lines).")
            scan_y_coords = scan_y_coords_base
    else:
        scan_y_coords = []


    # Intersect full lines with the polygon to get the segments needed for 100% coverage
    full_coverage_segments = []
    for y in scan_y_coords:
        line = LineString([(min_x - (max_x-min_x), y), (max_x + (max_x-min_x), y)]) # Extend lines far out
        intersection = rotated_polygon.intersection(line)
        
        if not intersection.is_empty:
            if intersection.geom_type == 'MultiLineString':
                full_coverage_segments.extend(list(intersection.geoms))
            elif intersection.geom_type == 'LineString':
                full_coverage_segments.append(intersection)

    # 5. STAGE 2: Shorten each segment from the boundary by half the sensor width.
    # This ensures the *edge of the coverage buffer* aligns precisely with the geofence.
    all_segments = []
    for seg in full_coverage_segments:
        # Reduce the shortening distance slightly to push coverage into the corners.
        shortened_seg = shorten_segment(seg, inset_dist_deg_lat * 0.75)
        all_segments.append(shortened_seg)

    if not all_segments:
        return []

    # 6. Build the final path by stitching the efficient segments
    ordered_path_rotated = []
    
    start_distances = [seg.distance(rotated_entry_point) for seg in all_segments]
    current_index = np.argmin(start_distances)
    current_segment = all_segments.pop(current_index)
    
    start_node, end_node = Point(current_segment.coords[0]), Point(current_segment.coords[-1])
    if start_node.distance(rotated_entry_point) > end_node.distance(rotated_entry_point):
        ordered_path_rotated.extend(list(current_segment.coords)[::-1])
    else:
        ordered_path_rotated.extend(list(current_segment.coords))
        
    while all_segments:
        last_point = Point(ordered_path_rotated[-1])
        best_dist, best_index, reverse_needed = float('inf'), -1, False
        
        for i, segment in enumerate(all_segments):
            start, end = Point(segment.coords[0]), Point(segment.coords[-1])
            dist_to_start, dist_to_end = last_point.distance(start), last_point.distance(end)
            
            if dist_to_start < best_dist:
                best_dist, best_index, reverse_needed = dist_to_start, i, False
            if dist_to_end < best_dist:
                best_dist, best_index, reverse_needed = dist_to_end, i, True
        
        next_segment = all_segments.pop(best_index)
        segment_coords = list(next_segment.coords)
        if reverse_needed:
            ordered_path_rotated.extend(segment_coords[::-1])
        else:
            ordered_path_rotated.extend(segment_coords)
            
    # 7. Rotate the final path back to its original geographic orientation
    final_path_points = [affinity.rotate(Point(p), angle_deg, origin=rotation_origin, use_radians=False) for p in ordered_path_rotated]
    final_path = [(p.x, p.y) for p in final_path_points]
    
    final_path.insert(0, entry_point.coords[0])
    # Remove duplicates that might result from stitching
    unique_path = []
    for p in final_path:
        if not unique_path or Point(p).distance(Point(unique_path[-1])) > 1e-9:
            unique_path.append(p)

    if verbose:
        print(f"  Generated {len(full_coverage_segments)} path segments.")
        print(f"  Final path has {len(unique_path)} waypoints.")
        print("------------------------------------")

    return unique_path


def prune_tail_by_entry_distance(path_points, entry_point, geofence_polygon, sensor_footprint_width, total_tail_gain_threshold=0.005):
    """
    Finds the waypoint farthest from the entry. If the path segment after that
    point provides negligible new coverage, it is pruned.
    """
    if not path_points or len(path_points) < 4:
        return path_points

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    total_geofence_area = geofence_polygon.area if geofence_polygon.area > 0 else 1.0

    # Find the point in the path farthest from the entry point
    dists_from_entry = [Point(p).distance(entry_point) for p in path_points]
    apex_index = np.argmax(dists_from_entry)

    # If the apex is the end, there's nothing to prune
    if apex_index >= len(path_points) - 1:
        return path_points

    # Compare coverage of the full path vs. the path up to the apex
    full_path_line = LineString(path_points)
    full_coverage_area = full_path_line.buffer(sensor_buffer_deg, cap_style=3).intersection(geofence_polygon).area

    prefix_path = path_points[:apex_index + 1]
    prefix_line = LineString(prefix_path)
    prefix_coverage_area = prefix_line.buffer(sensor_buffer_deg, cap_style=3).intersection(geofence_polygon).area

    # Calculate the marginal gain from the "return trip"
    tail_gain_ratio = (full_coverage_area - prefix_coverage_area) / total_geofence_area

    if tail_gain_ratio < total_tail_gain_threshold:
        return prefix_path # Prune the tail
    else:
        return path_points # Keep the tail


def plot_path_comparison(geofence_polygon, path_before, path_after, sensor_footprint_width, gaps=None):
    """Plots two paths side-by-side for comparison."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat

    for ax, path, title in [(ax1, path_before, 'Before Refinement'), (ax2, path_after, 'After Gap Closing')]:
        # Geofence
        gx, gy = geofence_polygon.exterior.xy
        ax.plot(gx, gy, label='Geofence', color='blue', linewidth=2)
        
        # Surveyed Area
        if path and len(path) > 1:
            line = LineString(path)
            surveyed = line.buffer(sensor_buffer_deg, cap_style=2)
            if surveyed.geom_type in ('Polygon', 'MultiPolygon'):
                polys = list(surveyed.geoms) if hasattr(surveyed, 'geoms') else [surveyed]
                for i, poly in enumerate(polys):
                    sx, sy = poly.exterior.xy
                    ax.fill(sx, sy, alpha=0.3, fc='lightgreen', ec='none', label='Surveyed' if i==0 else "")

            # Path
            px = [p[0] for p in path]
            py = [p[1] for p in path]
            ax.plot(px, py, marker='o', linestyle='-', markersize=3, color='red', label='UAV Path')

        ax.set_title(title)
        ax.legend()
        ax.grid(True)
        ax.axis('equal')

    if gaps and ax2:
        for i, gap in enumerate(gaps):
            if not gap.is_empty:
                gx, gy = gap.exterior.xy
                ax2.fill(gx, gy, alpha=0.5, fc='orange', ec='none', label='Detected Gap' if i==0 else "")
        ax2.legend()
        
    plt.suptitle('Path Refinement Comparison')
    plt.show()


def refine_path_with_local_cascade(geofence_polygon, base_path, sensor_footprint_width,
                                     max_cascade_steps=3, min_final_overlap=0.15):
    """
    Finds outer gap and pulls sweeps outward in a limited, local cascade.
    """
    if not base_path or len(base_path) < 4: return base_path

    current_path = list(base_path)
    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat

    for cascade_step in range(max_cascade_steps):
        uncovered = geofence_polygon.difference(LineString(current_path).buffer(sensor_buffer_deg))
        if uncovered.is_empty or (uncovered.area / geofence_polygon.area) < 0.001: break
        
        gaps = [p for p in (list(uncovered.geoms) if hasattr(uncovered, 'geoms') else [uncovered]) if p.area > 0]
        if not gaps: break
        largest_gap = max(gaps, key=lambda p: p.area)

        all_segments = [{'line': LineString(current_path[i:i+2]), 'index': i} for i in range(len(current_path) - 1)]
        length_threshold = np.median([s['line'].length for s in all_segments]) if all_segments else 0
        path_sweeps = [s for s in all_segments if s['line'].length >= length_threshold]
        if len(path_sweeps) < 2: break

        s_closest = min(path_sweeps, key=lambda s: s['line'].distance(largest_gap))
        
        p_start, p_end = s_closest['line'].coords
        line_vec = np.array(p_end) - np.array(p_start)
        perp_vec = np.array([-line_vec[1], line_vec[0]]) / np.linalg.norm(line_vec)
        if np.dot(perp_vec, np.array(largest_gap.centroid.coords[0]) - np.array(s_closest['line'].centroid.coords[0])) < 0:
            perp_vec *= -1.0
            
        sweeps_ordered = sorted(path_sweeps, key=lambda s: np.dot(perp_vec, np.array(s['line'].centroid.coords[0])))
        
        if cascade_step >= len(sweeps_ordered): break
        target_sweep = sweeps_ordered[-(cascade_step + 1)]
        
        block_indices = range(target_sweep['index'] + 2)

        max_boundary_shift = 0
        for test_dist in np.linspace(sensor_buffer_deg, 0, 10):
            test_vec = perp_vec * test_dist
            shifted_block = [(p[0]+test_vec[0], p[1]+test_vec[1]) for p in [current_path[i] for i in block_indices]]
            if LineString(shifted_block).within(geofence_polygon.buffer(-1e-9)):
                max_boundary_shift = test_dist
                break
        
        max_overlap_shift = float('inf')
        if cascade_step > 0:
            outer_neighbor = sweeps_ordered[-(cascade_step)]
            line1 = LineString(current_path[target_sweep['index'] : target_sweep['index']+2])
            line2 = LineString(current_path[outer_neighbor['index'] : outer_neighbor['index']+2])
            current_dist = line1.distance(line2)
            desired_dist = sensor_buffer_deg * 2 * (1 - min_final_overlap)
            # This is the corrected logic: shift is the amount needed to restore distance
            max_overlap_shift = current_dist - desired_dist

        actual_shift_dist = max(0, min(max_boundary_shift, max_overlap_shift))

        if actual_shift_dist > 1e-9:
            shift_vector = perp_vec * actual_shift_dist
            print(f"Cascade {cascade_step+1}: Shifting block for sweep {target_sweep['index']} by {actual_shift_dist:.6f}")
            for j in block_indices:
                pt = current_path[j]
                current_path[j] = (pt[0] + shift_vector[0], pt[1] + shift_vector[1])
        else:
            break

    return current_path


def get_k_closest_corners(geofence_polygon, uav_start_position, k=3):
    """
    Returns up to k closest distinct corners of the geofence to the UAV start.
    """
    corners = [Point(c) for c in geofence_polygon.exterior.coords[:-1]]
    corners_sorted = sorted(corners, key=lambda p: uav_start_position.distance(p))
    unique = []
    seen = set()
    for pt in corners_sorted:
        key = (round(pt.x, 12), round(pt.y, 12))
        if key in seen:
            continue
        seen.add(key)
        unique.append(pt)
        if len(unique) == k:
            break
    return unique

def compute_path_metrics(geofence_polygon, path_points, sensor_footprint_width):
    """
    Computes coverage ratio and path length. Returns (0.0, inf) if path is outside geofence.
    """
    if not path_points or len(path_points) < 2:
        return 0.0, float('inf')

    path_line = LineString(path_points)
    # Critical Check: Ensure the entire path is contained by the geofence.
    # A small positive buffer is used to account for floating point inaccuracies.
    if not geofence_polygon.buffer(1e-9).covers(path_line):
        return 0.0, float('inf') # Automatic fail

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    surveyed_area = path_line.buffer(sensor_buffer_deg, cap_style=3)
    covered_area = surveyed_area.intersection(geofence_polygon).area
    total_area = geofence_polygon.area if geofence_polygon.area > 0 else 1.0
    coverage_ratio = covered_area / total_area
    path_length = path_line.length
    return coverage_ratio, path_length


def choose_best_entry_point(geofence_polygon, uav_start_position, overlap, sensor_footprint_width):
    """
    Evaluates the three closest corners, considering both long-axis and short-axis
    paths, filtering for >0.9 coverage, and then selecting the one that
    provides the minimum path length.
    Returns (best_entry_point, best_path, debug_metrics_list, candidates, candidate_paths, best_index).
    """
    candidates = get_k_closest_corners(geofence_polygon, uav_start_position, k=3)
    debug = []
    candidate_paths = []
    results = []

    for idx, candidate in enumerate(candidates):
        # Generate both long-axis and short-axis paths
        for force_short in [False, True]:
            candidate_path = generate_surveillance_path(
                geofence_polygon, overlap, sensor_footprint_width, candidate, verbose=False, force_short_axis=force_short
            )
            # candidate_paths.append(candidate_path) # This needs adjustment to show the best path
            coverage, length = compute_path_metrics(
                geofence_polygon, candidate_path, sensor_footprint_width
            )
            
            metrics = {
                'corner_index': idx,
                'entry_point': (candidate.x, candidate.y),
                'coverage_ratio': coverage,
                'path_length_deg': length,
                'waypoints': len(candidate_path) if candidate_path else 0,
                'candidate': candidate,
                'path': candidate_path,
                'short_axis': force_short,
            }
            results.append(metrics)
            # Store all generated paths for potential plotting, though we only plot the best per corner
            if idx < len(candidate_paths):
                # Simple logic: keep the one with better score for plotting
                current_best_score = compute_path_metrics(geofence_polygon, candidate_paths[idx], sensor_footprint_width)
                if (coverage, -length) > (current_best_score[0], -current_best_score[1]):
                    candidate_paths[idx] = candidate_path
            else:
                candidate_paths.append(candidate_path)
    
    # Update debug to include all attempts
    debug = results

    if not results:
        # Fallback to closest corner if no paths could be generated
        fallback = find_entry_corner(geofence_polygon, uav_start_position)
        path = generate_surveillance_path(geofence_polygon, overlap, sensor_footprint_width, fallback, verbose=False)
        coverage, length = compute_path_metrics(geofence_polygon, path, sensor_footprint_width)
        debug.append({
            'corner_index': -1, 'entry_point': (fallback.x, fallback.y), 'coverage_ratio': coverage,
            'path_length_deg': length, 'waypoints': len(path) if path else 0
        })
        return fallback, path, debug, [fallback], [path], 0

    # New Selection Logic:
    # 1. Filter for candidates that meet the coverage threshold
    coverage_threshold = 0.9
    valid_candidates = [r for r in results if r['coverage_ratio'] >= coverage_threshold]
    
    # 2. If some candidates meet the threshold, choose from them. Otherwise, use all candidates.
    pool = valid_candidates if valid_candidates else results
    
    # 3. Select the best candidate from the pool based on minimum path length.
    if not pool: # If all paths failed validation, there is no best.
        # This case should ideally not be hit if fallback works, but as a safeguard:
        return candidates[0], [], [], candidates, [], 0
    
    best_candidate = min(pool, key=lambda r: r['path_length_deg'])
    
    best_entry = best_candidate['candidate']
    best_path = best_candidate['path']
    best_index = best_candidate['corner_index']
    
    # The candidate_paths list for plotting should contain the best path for each corner to avoid confusion
    final_candidate_paths = []
    for i in range(len(candidates)):
        paths_for_corner = [r['path'] for r in results if r['corner_index'] == i]
        metrics_for_corner = [r for r in results if r['corner_index'] == i]
        if not metrics_for_corner:
            final_candidate_paths.append([])
            continue
        
        valid_paths = [r for r in metrics_for_corner if r['coverage_ratio'] >= coverage_threshold]
        pool = valid_paths if valid_paths else metrics_for_corner
        best_path_for_corner = min(pool, key=lambda r: r['path_length_deg'])['path']
        final_candidate_paths.append(best_path_for_corner)

    return best_entry, best_path, debug, candidates, final_candidate_paths, best_candidate


def plot_candidate_paths(geofence_polygon, candidates, candidate_paths_by_corner, metrics, best_choice, sensor_footprint_width):
    """
    Plots simulated paths for each candidate corner, showing both long-axis
    and short-axis strategies in a 2xN grid.
    """
    if not candidates: return
    n_corners = len(candidates)
    fig, axes = plt.subplots(2, n_corners, figsize=(6 * n_corners, 10))
    if n_corners == 1: axes = np.array([[axes], [axes]]) # Adjust shape for single corner

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat

    for i in range(n_corners):
        for j, is_short_axis in enumerate([False, True]):
            ax = axes[j, i]
            axis_label = "Short Axis" if is_short_axis else "Long Axis"
            
            # Find the correct path and metrics
            path = None
            path_metrics = None
            for m in metrics:
                if m['corner_index'] == i and m['short_axis'] == is_short_axis:
                    path = m['path']
                    path_metrics = m
                    break

            # Geofence
            gx, gy = geofence_polygon.exterior.xy
            ax.plot(gx, gy, color='blue', linewidth=2, label='Geofence', zorder=2)
            
            # Path and Coverage
            if path and len(path) > 1:
                line = LineString(path)
                surveyed = line.buffer(sensor_buffer_deg, cap_style=2)
                if not surveyed.is_empty:
                    sx, sy = surveyed.exterior.xy if surveyed.geom_type == 'Polygon' else ([], [])
                    if surveyed.geom_type == 'Polygon': ax.fill(sx, sy, alpha=0.25, fc='lightgreen', ec='none', label='Coverage', zorder=1)
                    elif surveyed.geom_type == 'MultiPolygon':
                        for poly in surveyed.geoms:
                            px, py = poly.exterior.xy
                            ax.fill(px, py, alpha=0.25, fc='lightgreen', ec='none', zorder=1)

                px = [p[0] for p in path]
                py = [p[1] for p in path]
                ax.plot(px, py, color='red', marker='o', markersize=3, linewidth=1.5, label='Path', zorder=3)

            # Entry marker
            entry = candidates[i]
            ax.plot(entry.x, entry.y, marker='*', color='green', markersize=14, label='Entry', zorder=4)

            # Title with metrics
            cov = path_metrics['coverage_ratio'] if path_metrics else 0.0
            length_deg = path_metrics['path_length_deg'] if path_metrics else 0.0
            length_km = length_deg * 111.320  # Convert degrees to km
            
            tag = ""
            if best_choice and best_choice['corner_index'] == i and best_choice['short_axis'] == is_short_axis:
                tag = " (Best)"

            ax.set_title(f"Corner {i} - {axis_label}{tag}\ncoverage={cov:.2%}, length={length_km:.3f} km")
            ax.legend(loc='lower left', fontsize=8)
            ax.grid(True)
            ax.axis('equal')

    fig.suptitle('Simulated Paths per Candidate Entry Corner (Long vs Short Axis)', fontsize=14)
    plt.tight_layout()
    plt.show()


def choose_best_overlap(geofence_polygon, entry_point, base_overlap, sensor_footprint_width, num_samples=4):
    """
    Samples overlap values, testing BOTH long and short axis paths for each,
    filters for >0.9 coverage, and selects the one with min length.
    Returns (best_overlap, best_path, metrics, overlaps, paths, best_index, best_short_axis_flag).
    """
    high = base_overlap
    low = max(0.0, base_overlap - 0.001)
    n = max(2, int(num_samples))
    overlaps = list(np.linspace(high, low, n))

    metrics = []
    results = []
    
    for idx, ov in enumerate(overlaps):
        for force_short in [False, True]:
            path = generate_surveillance_path(geofence_polygon, ov, sensor_footprint_width, entry_point, verbose=False, force_short_axis=force_short)
            coverage, length = compute_path_metrics(geofence_polygon, path, sensor_footprint_width)
            
            result_metrics = {
                'index': idx, 'overlap': ov, 'coverage_ratio': coverage, 
                'path_length_deg': length, 'waypoints': len(path) if path else 0,
                'path': path, 'short_axis': force_short
            }
            results.append(result_metrics)
            metrics.append(result_metrics)

    if not results: return base_overlap, [], [], overlaps, [], 0, False

    coverage_threshold = 0.9
    valid_candidates = [r for r in results if r['coverage_ratio'] >= coverage_threshold]
    pool = valid_candidates if valid_candidates else results
    if not pool: return base_overlap, [], [], overlaps, [], 0, False

    best_candidate = min(pool, key=lambda r: r['path_length_deg'])
    
    # We need to return all paths for plotting
    all_paths = [r['path'] for r in sorted(results, key=lambda x: (x['index'], x['short_axis']))]

    return best_candidate['overlap'], best_candidate['path'], metrics, overlaps, all_paths, best_candidate['index'], best_candidate['short_axis']


def plot_overlap_candidates(geofence_polygon, entry_point, overlaps, paths, metrics, best_index, best_is_short, sensor_footprint_width):
    """
    Plots simulated paths for candidate overlap values, showing both long and short axis.
    """
    if not overlaps: return
    n_overlaps = len(overlaps)
    fig, axes = plt.subplots(2, n_overlaps, figsize=(6 * n_overlaps, 10))
    if n_overlaps == 1: axes = np.array([[axes], [axes]])

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat

    for i in range(n_overlaps):
        for j, is_short_axis in enumerate([False, True]):
            ax = axes[j, i]
            path_idx = i * 2 + j
            path = paths[path_idx] if path_idx < len(paths) else []
            
            # Find corresponding metrics
            metric = None
            for m in metrics:
                if m['index'] == i and m['short_axis'] == is_short_axis:
                    metric = m
                    break
            
            gx, gy = geofence_polygon.exterior.xy
            ax.plot(gx, gy, color='blue', linewidth=2, label='Geofence', zorder=2)

            if path and len(path) > 1:
                line = LineString(path)
                surveyed = line.buffer(sensor_buffer_deg, cap_style=2)
                if not surveyed.is_empty:
                    if surveyed.geom_type == 'Polygon':
                        sx, sy = surveyed.exterior.xy
                        ax.fill(sx, sy, alpha=0.25, fc='lightgreen', ec='none', label='Coverage', zorder=1)
                    elif surveyed.geom_type == 'MultiPolygon':
                        for poly in surveyed.geoms:
                            px_s, py_s = poly.exterior.xy
                            ax.fill(px_s, py_s, alpha=0.25, fc='lightgreen', ec='none', zorder=1)

                px = [p[0] for p in path]
                py = [p[1] for p in path]
                ax.plot(px, py, color='red', marker='o', markersize=3, linewidth=1.5, label='Path', zorder=3)
            
            ax.plot(entry_point.x, entry_point.y, marker='*', color='green', markersize=14, label='Entry', zorder=4)
            
            cov = metric['coverage_ratio'] if metric else 0.0
            length_deg = metric['path_length_deg'] if metric else 0.0
            length_km = length_deg * 111.320  # Convert degrees to km
            ov = overlaps[i]
            axis_label = "Short Axis" if is_short_axis else "Long Axis"
            tag = " (Best)" if i == best_index and is_short_axis == best_is_short else ""
            
            ax.set_title(f"overlap={ov:.4f} - {axis_label}{tag}\ncoverage={cov:.2%}, length={length_km:.3f} km")
            ax.legend(loc='lower left', fontsize=8)
            ax.grid(True)
            ax.axis('equal')

    fig.suptitle('Simulated Paths for Candidate Overlap Values (Long vs Short Axis)', fontsize=14)
    plt.tight_layout()
    plt.show()

def plot_tail_overlap_adjustments(geofence_polygon, base_path, candidates, sensor_footprint_width, titles):
    """
    Visualize base path vs tail-overlap-adjusted candidates side-by-side.
    candidates: list of path lists (may include None). titles: list of labels.
    """
    items = [("Base (no tail change)", base_path)] + list(zip(titles, candidates))
    items = [(t, p) for t, p in items if p and len(p) > 1]
    if len(items) < 2:
        return
    n = len(items)
    fig, axes = plt.subplots(1, n, figsize=(6 * n, 5))
    if n == 1:
        axes = [axes]
    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    for ax, (title, path) in zip(axes, items):
        gx, gy = geofence_polygon.exterior.xy
        ax.plot(gx, gy, color='blue', linewidth=2, label='Geofence', zorder=2)
        line = LineString(path)
        surveyed = line.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon)
        if not surveyed.is_empty:
            if surveyed.geom_type == 'Polygon':
                sx, sy = surveyed.exterior.xy
                ax.fill(sx, sy, alpha=0.25, fc='lightgreen', ec='none', label='Coverage', zorder=1)
            elif surveyed.geom_type == 'MultiPolygon':
                for poly in surveyed.geoms:
                    px, py = poly.exterior.xy
                    ax.fill(px, py, alpha=0.25, fc='lightgreen', ec='none', zorder=1)
        px = [p[0] for p in path]
        py = [p[1] for p in path]
        ax.plot(px, py, color='red', marker='o', markersize=3, linewidth=1.5, label='Path', zorder=3)
        ax.set_title(title)
        ax.legend(loc='lower left', fontsize=8)
        ax.grid(True)
        ax.axis('equal')
    fig.suptitle('Tail Overlap Adjustments (comparison)', fontsize=14)
    plt.tight_layout()
    plt.show()

def refine_tail_by_boundary_band(geofence_polygon, base_path, base_overlap, sensor_footprint_width,
                                 max_decrease=0.0005, min_overlap=0.15, area_gain_epsilon=1e-6,
                                 max_length_factor=1.03, max_iters=2):
    """
    Adaptive refinement: measure uncovered boundary-connected area and locally
    regenerate only the final sweep(s) with overlap derived from uncovered band width.
    Returns possibly improved path and optional comparison plot.
    """
    if not base_path or len(base_path) < 6:
        return base_path

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    line = LineString(base_path)
    surveyed = line.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon)
    uncovered = geofence_polygon.difference(surveyed)
    if uncovered.is_empty:
        return base_path

    # Keep components touching boundary only
    boundary = geofence_polygon.boundary
    components = []
    if uncovered.geom_type == 'Polygon':
        polys = [uncovered]
    elif uncovered.geom_type == 'MultiPolygon':
        polys = list(uncovered.geoms)
    else:
        polys = []
    for poly in polys:
        if not poly.is_empty and poly.boundary.crosses(boundary) or poly.touches(boundary):
            components.append(poly)
    if not components:
        return base_path

    # Estimate min band width among components
    def estimate_band_width(poly):
        # Use average of distances from polygon interior sample points to boundary
        try:
            sample = poly.representative_point()
            d = sample.distance(boundary)
            return max(d, 0.0)
        except Exception:
            return 0.0

    min_band = min(estimate_band_width(c) for c in components)
    if min_band <= 0:
        return base_path

    # Try a couple of decreasing overlaps on the tail only
    tried_paths = []
    base_ln = LineString(base_path)
    base_cov = base_ln.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon).area
    base_len = base_ln.length
    for step in [max_decrease/2.0, max_decrease]:
        overlap_req = max(min_overlap, base_overlap - step)
        if overlap_req >= base_overlap - 1e-7:
            continue
        split = max(2, len(base_path) - 10)
        head = base_path[:split]
        tail_entry = Point(head[-1])
        new_tail = generate_surveillance_path(geofence_polygon, overlap_req, sensor_footprint_width, tail_entry, verbose=False)
        if not new_tail or len(new_tail) < 2:
            continue
        candidate = head + new_tail[1:]
        ln = LineString(candidate)
        cov = ln.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon).area
        length = ln.length
        tried_paths.append((candidate, overlap_req, cov, length))
        if cov >= base_cov + area_gain_epsilon and length <= base_len * max_length_factor:
            try:
                plot_tail_overlap_adjustments(geofence_polygon, base_path, [candidate], sensor_footprint_width,
                                              [f"overlap={overlap_req:.4f}, tail"])
            except Exception:
                pass
            print(f"Accepted tail refinement: overlap={overlap_req:.4f}, cov_gain={cov-base_cov:.6e}, len={length:.6f} <= {base_len*max_length_factor:.6f}")
            return candidate
    # If none accepted, show comparison for diagnostics
    if tried_paths:
        try:
            titles = [f"overlap={ov:.4f}, Δcov={(cv-base_cov):.2e}, Δlen={(ln-base_len):.2e}" for _, ov, cv, ln in tried_paths]
            paths_only = [p for p, _, _, _ in tried_paths]
            plot_tail_overlap_adjustments(geofence_polygon, base_path, paths_only, sensor_footprint_width, titles)
        except Exception:
            pass
    return base_path

def shortcut_redundant_waypoints(path_points, geofence_polygon, sensor_footprint_width, coverage_loss_threshold=0.005, debug=False):
    """
    Removes redundant intermediate waypoints by checking if we can skip them
    while maintaining coverage. This is more general than just trimming the tail.
    
    For each waypoint, checks if we can skip to i+2, i+3, etc. while maintaining
    the same coverage (within threshold).
    
    coverage_loss_threshold: Maximum acceptable coverage loss (as fraction of total area)
    """
    if not path_points or len(path_points) < 3:
        return path_points
    
    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    total_area = geofence_polygon.area if geofence_polygon.area > 0 else 1.0
    
    # Get initial coverage - this is our baseline that we must maintain
    initial_line = LineString(path_points)
    initial_coverage = initial_line.buffer(sensor_buffer_deg, cap_style=3).intersection(geofence_polygon).area
    
    if debug:
        print(f"    [Debug] Starting shortcut optimization: {len(path_points)} waypoints")
        print(f"    [Debug] Initial coverage: {initial_coverage/total_area:.4f}")
        print(f"    [Debug] Maximum allowed total coverage loss: {coverage_loss_threshold:.4f}")
    
    simplified = list(path_points)
    i = 0
    shortcuts_made = 0
    
    while i < len(simplified) - 2:
        # Try to skip ahead from waypoint i
        best_skip = 0
        
        # Try skipping 1, 2, 3... waypoints ahead
        # Be conservative - only try skipping up to 3 waypoints at a time
        max_skip = min(4, len(simplified) - i - 1)
        
        for skip_count in range(1, max_skip):
            # Create path with shortcut: keep points 0..i, skip to i+skip_count+1, keep rest
            test_path = simplified[:i+1] + simplified[i+skip_count+1:]
            
            # Calculate coverage with this shortcut
            test_line = LineString(test_path)
            test_coverage = test_line.buffer(sensor_buffer_deg, cap_style=3).intersection(geofence_polygon).area
            
            # IMPORTANT: Compare against INITIAL coverage to prevent cumulative loss
            total_coverage_loss = (initial_coverage - test_coverage) / total_area
            
            if total_coverage_loss <= coverage_loss_threshold:
                best_skip = skip_count
                if debug:
                    print(f"      WP{i} → WP{i+skip_count+1}: Can skip {skip_count} waypoint(s), total_loss={total_coverage_loss:.6f} ✓")
                # Don't break - keep checking if we can skip even more
            else:
                if debug and skip_count == 1:
                    print(f"      WP{i}: Cannot skip (total_loss would be {total_coverage_loss:.6f})")
                break  # Can't skip this many, stop trying
        
        if best_skip > 0:
            # Apply the best shortcut and update our working path
            removed = simplified[i+1:i+best_skip+1]
            simplified = simplified[:i+1] + simplified[i+best_skip+1:]
            shortcuts_made += 1
            if debug:
                print(f"        ✂️ Applied shortcut: removed {len(removed)} waypoint(s)")
        else:
            i += 1  # Move to next waypoint
    
    if debug:
        print(f"    [Debug] Shortcut optimization complete: {len(path_points)} → {len(simplified)} waypoints")
        print(f"    [Debug] Made {shortcuts_made} shortcuts")
        
        # Verify final coverage
        final_line = LineString(simplified)
        final_coverage = final_line.buffer(sensor_buffer_deg, cap_style=3).intersection(geofence_polygon).area
        actual_loss = (initial_coverage - final_coverage) / total_area
        print(f"    [Debug] Final coverage: {final_coverage/total_area:.4f} (actual loss: {actual_loss:.6f})")
        if actual_loss > coverage_loss_threshold:
            print(f"    [Debug] ⚠️ WARNING: Exceeded threshold by {(actual_loss - coverage_loss_threshold):.6f}")
    
    return simplified

def trim_redundant_tail(path_points, geofence_polygon, sensor_footprint_width, relative_gain_threshold=0.003, debug=False):
    """
    Iteratively removes tail waypoints whose buffered coverage adds negligible
    new area inside the geofence. This avoids unnecessary backtracking legs.
    relative_gain_threshold is the minimum fractional area gain (w.r.t. geofence
    area) required to keep the last waypoint.
    """
    if not path_points or len(path_points) < 3:
        return path_points

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    total_area = geofence_polygon.area if geofence_polygon.area > 0 else 1.0

    trimmed = list(path_points)
    improved = True
    iteration = 0
    if debug:
        print(f"    [Debug] Starting with {len(trimmed)} waypoints, threshold={relative_gain_threshold:.6f}")
    
    while improved and len(trimmed) > 2:
        improved = False
        iteration += 1
        full_line = LineString(trimmed)
        prev_line = LineString(trimmed[:-1])
        full_cov = full_line.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon).area
        prev_cov = prev_line.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon).area
        gain = full_cov - prev_cov
        gain_ratio = gain / total_area
        
        if debug:
            print(f"      Iteration {iteration}: Checking WP {len(trimmed)-1}, gain={gain_ratio:.6f} ({'DROP' if gain_ratio < relative_gain_threshold else 'KEEP'})")
        
        if gain_ratio < relative_gain_threshold:
            removed_wp = trimmed.pop()  # drop last waypoint
            if debug:
                print(f"        ✂️ Removed waypoint {len(trimmed)}: {removed_wp}")
            improved = True
    
    if debug and len(trimmed) < len(path_points):
        print(f"    [Debug] Trimmed from {len(path_points)} → {len(trimmed)} waypoints")
    
    return trimmed

def prune_path_by_coverage_barrier(path_points, geofence_polygon, sensor_footprint_width,
                                   coverage_barrier_ratio=0.985, min_marginal_gain_ratio_per_deg=0.002,
                                   consecutive_steps=2, debug=False):
    """
    Prunes the path tail once overall coverage crosses a barrier ratio of the
    geofence area and the marginal coverage gain per additional path length
    falls below a small threshold for a few consecutive steps.

    coverage_barrier_ratio: fraction of geofence area to guarantee (e.g., 0.985)
    min_marginal_gain_ratio_per_deg: minimum acceptable gain in area per extra
        degree of path length, normalized by geofence area.
    consecutive_steps: require this many consecutive low-gain steps before cut.
    """
    if not path_points or len(path_points) < 4:
        return path_points

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    total_area = geofence_polygon.area if geofence_polygon.area > 0 else 1.0

    cumulative_length = 0.0
    prev_point = None
    coverages = []
    lengths = []

    for i, p in enumerate(path_points):
        if i == 0:
            prev_point = p
            coverages.append(0.0)
            lengths.append(0.0)
            continue
        seg_len = Point(prev_point).distance(Point(p))
        cumulative_length += seg_len
        prefix_line = LineString(path_points[:i+1])
        cov = prefix_line.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon).area
        coverages.append(cov)
        lengths.append(cumulative_length)
        prev_point = p

    barrier = coverage_barrier_ratio * total_area
    low_gain_streak = 0
    cut_index = None
    
    if debug:
        print(f"    [Debug] Barrier threshold: {barrier:.6e} (target coverage ratio: {coverage_barrier_ratio})")
        print(f"    [Debug] Minimum marginal gain: {min_marginal_gain_ratio_per_deg:.6f}")
        print(f"    [Debug] Analyzing {len(path_points)} waypoints...")
        print(f"    [Debug] Waypoint analysis (showing last 15):")
    
    for i in range(2, len(path_points)):
        cov = coverages[i]
        cov_prev = coverages[i-1]
        len_i = lengths[i]
        len_prev = lengths[i-1]
        len_gain = max(1e-12, len_i - len_prev)
        marginal = (cov - cov_prev) / total_area / len_gain
        
        # Show detailed info for last 15 waypoints if debug
        if debug and i >= len(path_points) - 15:
            status = "ABOVE_BARRIER" if cov >= barrier else "BELOW_BARRIER"
            gain_status = "LOW_GAIN" if marginal < min_marginal_gain_ratio_per_deg else "HIGH_GAIN"
            print(f"      WP{i:3d}: cov={cov/total_area:.4f} ({status}), marginal={marginal:.6f} ({gain_status}), streak={low_gain_streak}")
        
        if cov >= barrier and marginal < min_marginal_gain_ratio_per_deg:
            low_gain_streak += 1
            if debug and low_gain_streak == 1:
                print(f"    [Debug] ⚠ Low-gain streak STARTED at waypoint {i}")
            if low_gain_streak >= consecutive_steps:
                cut_index = i - consecutive_steps
                if debug:
                    print(f"    [Debug] ✂️ CUT triggered at waypoint {cut_index} (removing {len(path_points) - cut_index - 1} waypoints)")
                break
        else:
            if low_gain_streak > 0 and debug:
                print(f"    [Debug] ↻ Streak RESET at waypoint {i} (was {low_gain_streak} steps)")
            low_gain_streak = 0

    if cut_index is not None and cut_index >= 2:
        return path_points[:cut_index+1]
    return path_points

def prune_return_with_low_gain(path_points, entry_point, geofence_polygon, sensor_footprint_width,
                               coverage_barrier_ratio=0.985, min_marginal_gain_ratio_per_deg=0.003,
                               consecutive_steps=2, min_return_delta_deg=0.0005):
    """
    After crossing a coverage barrier, if the path begins to systematically
    move closer to the entry while adding very little new coverage, cut the
    path at the start of that return motion.
    """
    if not path_points or len(path_points) < 4:
        return path_points

    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    total_area = geofence_polygon.area if geofence_polygon.area > 0 else 1.0

    # Precompute cumulative coverage and length
    coverages = [0.0]
    lengths = [0.0]
    cumulative_length = 0.0
    for i in range(1, len(path_points)):
        p_prev = Point(path_points[i-1])
        p_cur = Point(path_points[i])
        cumulative_length += p_prev.distance(p_cur)
        prefix_line = LineString(path_points[:i+1])
        cov = prefix_line.buffer(sensor_buffer_deg, cap_style=2).intersection(geofence_polygon).area
        coverages.append(cov)
        lengths.append(cumulative_length)

    barrier = coverage_barrier_ratio * total_area
    dists_to_entry = [Point(p).distance(entry_point) for p in path_points]

    low_gain_streak = 0
    return_streak = 0
    start_idx = None

    for i in range(2, len(path_points)):
        if coverages[i] < barrier:
            continue
        # Marginal gain
        len_gain = max(1e-12, lengths[i] - lengths[i-1])
        marginal = (coverages[i] - coverages[i-1]) / total_area / len_gain
        low_gain = marginal < min_marginal_gain_ratio_per_deg

        # Returning toward entry?
        moving_closer = (dists_to_entry[i-1] - dists_to_entry[i]) > 0
        return_amount = dists_to_entry[i-1] - dists_to_entry[i]

        low_gain_streak = low_gain_streak + 1 if low_gain else 0
        return_streak = return_streak + 1 if (moving_closer and return_amount >= min_return_delta_deg) else 0

        if low_gain_streak >= consecutive_steps and return_streak >= consecutive_steps:
            start_idx = i - consecutive_steps
            break

    if start_idx is not None and start_idx >= 2:
        return path_points[:start_idx+1]
    return path_points

def refine_path_by_gap_closing(geofence_polygon, base_path, sensor_footprint_width,
                               min_gap_area_ratio=0.001, gap_aspect_ratio_threshold=5.0,
                               nudge_fraction=0.6):
    """
    Identifies long, thin uncovered gaps between sweeps and adjusts the path by
    nudging adjacent sweeps closer to close the gap, then re-stitching the path.

    min_gap_area_ratio: Minimum area of a gap (as fraction of geofence) to consider.
    gap_aspect_ratio_threshold: A gap is a sliver if its length/width is above this.
    nudge_fraction: How much of the gap to close (e.g., 0.6 means move each sweep 30% inward).
    """
    if not base_path or len(base_path) < 4:
        return base_path, []

    # 1. Detect significant uncovered gaps
    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    base_line = LineString(base_path)
    surveyed_area = base_line.buffer(sensor_buffer_deg, cap_style=2)
    uncovered = geofence_polygon.difference(surveyed_area)
    
    if uncovered.is_empty:
        return base_path, []

    total_area = geofence_polygon.area
    min_gap_area = total_area * min_gap_area_ratio
    gaps = []
    
    polys = list(uncovered.geoms) if uncovered.geom_type == 'MultiPolygon' else [uncovered]
    for poly in polys:
        if poly.area < min_gap_area:
            continue
        # Check aspect ratio to identify slivers
        mbr = poly.minimum_rotated_rectangle
        mbr_coords = list(mbr.exterior.coords)
        edge1 = Point(mbr_coords[0]).distance(Point(mbr_coords[1]))
        edge2 = Point(mbr_coords[1]).distance(Point(mbr_coords[2]))
        if min(edge1, edge2) > 1e-9:
            aspect_ratio = max(edge1, edge2) / min(edge1, edge2)
            if aspect_ratio >= gap_aspect_ratio_threshold:
                gaps.append(poly)
    
    if not gaps:
        return base_path, []

    # 2. Find path sweeps (straight-line segments)
    all_segments = []
    for i in range(len(base_path) - 1):
        all_segments.append({'line': LineString([base_path[i], base_path[i+1]]), 'index': i})

    segment_lengths = [seg['line'].length for seg in all_segments]
    if not segment_lengths:
        return base_path, []
    
    length_threshold = np.median(segment_lengths)
    path_sweeps = [seg for seg in all_segments if seg['line'].length >= length_threshold]
    
    if len(path_sweeps) < 2: # Not enough sweeps to have a gap between them
        return base_path, []

    # 3. Associate gaps with adjacent sweeps and calculate adjustments
    for gap in gaps:
        gap_center = gap.centroid
        sweeps_sorted_by_dist = sorted(path_sweeps, key=lambda s: s['line'].distance(gap_center))
        
        s1 = sweeps_sorted_by_dist[0]
        s2 = None
        for candidate in sweeps_sorted_by_dist[1:]:
            vec1 = np.array(s1['line'].coords[1]) - np.array(s1['line'].coords[0])
            vec2 = np.array(candidate['line'].coords[1]) - np.array(candidate['line'].coords[0])
            if np.linalg.norm(vec1) > 0 and np.linalg.norm(vec2) > 0:
                unit_vec1 = vec1 / np.linalg.norm(vec1)
                unit_vec2 = vec2 / np.linalg.norm(vec2)
                if abs(abs(np.dot(unit_vec1, unit_vec2)) - 1.0) < 0.1:
                    s2 = candidate
                    break
        
        if not s2: continue

        if s1['index'] > s2['index']: s1, s2 = s2, s1

        p1, p2 = s1['line'].coords
        line_vec = np.array(p2) - np.array(p1)
        perp_vec = np.array([-line_vec[1], line_vec[0]])
        perp_vec /= np.linalg.norm(perp_vec)
        
        gap_vec = np.array([s2['line'].centroid.x - s1['line'].centroid.x, s2['line'].centroid.y - s1['line'].centroid.y])
        if np.dot(perp_vec, gap_vec) < 0:
            perp_vec *= -1.0
        
        # We want to move s2 (and everything after it) towards s1
        nudge_vector = -perp_vec * s1['line'].distance(s2['line']) * nudge_fraction
        
        split_idx = s1['index'] + 1
        
        # Safety Check: try full nudge, then reduce if it goes out of bounds
        for scale in [1.0, 0.75, 0.5, 0.25]:
            current_nudge = nudge_vector * scale
            
            downstream_indices = range(split_idx, len(base_path))
            
            temp_path = list(base_path)
            is_valid = True
            
            downstream_line_pts = []
            for i in downstream_indices:
                pt = temp_path[i]
                new_pt = (pt[0] + current_nudge[0], pt[1] + current_nudge[1])
                temp_path[i] = new_pt
                downstream_line_pts.append(new_pt)

            if not downstream_line_pts or len(downstream_line_pts) < 2:
                continue

            # Check if the moved part is inside the geofence
            moved_part_line = LineString(downstream_line_pts)
            # Use a small negative buffer to be safe from touching the boundary
            if moved_part_line.within(geofence_polygon.buffer(-1e-9)):
                print(f"Applying one-sided adjustment with scale {scale:.2f}")
                return temp_path, gaps # Success, return the valid path
        
        # If even the smallest nudge fails, return original path
        return base_path, gaps

    # If no gaps were processed
    return base_path, gaps


def plot_optimization_comparison(geofence_polygon, path_before, path_after, entry_point, sensor_footprint_width, 
                                 before_metrics, after_metrics):
    """
    Plots a side-by-side comparison of the path before and after optimization.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8))
    
    meters_per_degree_lat = 111320.0
    sensor_buffer_deg = (sensor_footprint_width / 2.0) / meters_per_degree_lat
    
    # Before optimization (left)
    gx, gy = geofence_polygon.exterior.xy
    ax1.plot(gx, gy, label='Geofence', color='blue', linewidth=2, zorder=3)
    
    if path_before and len(path_before) > 1:
        line = LineString(path_before)
        surveyed = line.buffer(sensor_buffer_deg, cap_style=3)  # Square caps for full coverage
        surveyed_clipped = surveyed.intersection(geofence_polygon)  # Clip to geofence
        if not surveyed_clipped.is_empty:
            if surveyed_clipped.geom_type == 'Polygon':
                sx, sy = surveyed_clipped.exterior.xy
                ax1.fill(sx, sy, alpha=0.35, fc='lightgreen', ec='none', label='Surveyed Area', zorder=1)
            elif surveyed_clipped.geom_type == 'MultiPolygon':
                for i, poly in enumerate(surveyed_clipped.geoms):
                    px, py = poly.exterior.xy
                    ax1.fill(px, py, alpha=0.35, fc='lightgreen', ec='none', 
                            label='Surveyed Area' if i == 0 else "", zorder=1)
        
        px = [p[0] for p in path_before]
        py = [p[1] for p in path_before]
        ax1.plot(px, py, marker='o', linestyle='-', markersize=4, color='red', label='UAV Path', zorder=4, linewidth=1.5)
    
    ax1.plot(entry_point.x, entry_point.y, marker='*', markersize=18, color='green', label='Entry Point', zorder=5)
    
    waypoints, coverage, length_km = before_metrics
    ax1.set_title(f'Before Optimization\nWaypoints: {waypoints} | Coverage: {coverage:.2%} | Length: {length_km:.3f} km', 
                  fontsize=12, fontweight='bold')
    ax1.legend(loc='best', fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.axis('equal')
    ax1.set_xlabel('Longitude')
    ax1.set_ylabel('Latitude')
    
    # After optimization (right)
    ax2.plot(gx, gy, label='Geofence', color='blue', linewidth=2, zorder=3)
    
    if path_after and len(path_after) > 1:
        line = LineString(path_after)
        surveyed = line.buffer(sensor_buffer_deg, cap_style=3)  # Square caps for full coverage
        surveyed_clipped = surveyed.intersection(geofence_polygon)  # Clip to geofence
        if not surveyed_clipped.is_empty:
            if surveyed_clipped.geom_type == 'Polygon':
                sx, sy = surveyed_clipped.exterior.xy
                ax2.fill(sx, sy, alpha=0.35, fc='lightgreen', ec='none', label='Surveyed Area', zorder=1)
            elif surveyed_clipped.geom_type == 'MultiPolygon':
                for i, poly in enumerate(surveyed_clipped.geoms):
                    px, py = poly.exterior.xy
                    ax2.fill(px, py, alpha=0.35, fc='lightgreen', ec='none', 
                            label='Surveyed Area' if i == 0 else "", zorder=1)
        
        px = [p[0] for p in path_after]
        py = [p[1] for p in path_after]
        ax2.plot(px, py, marker='o', linestyle='-', markersize=4, color='red', label='UAV Path', zorder=4, linewidth=1.5)
    
    ax2.plot(entry_point.x, entry_point.y, marker='*', markersize=18, color='green', label='Entry Point', zorder=5)
    
    waypoints, coverage, length_km = after_metrics
    ax2.set_title(f'After Optimization\nWaypoints: {waypoints} | Coverage: {coverage:.2%} | Length: {length_km:.3f} km', 
                  fontsize=12, fontweight='bold')
    ax2.legend(loc='best', fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.axis('equal')
    ax2.set_xlabel('Longitude')
    ax2.set_ylabel('Latitude')
    
    plt.suptitle('Path Optimization Comparison', fontsize=16, fontweight='bold', y=0.98)
    plt.tight_layout()
    plt.show()


def plot_path(geofence_polygon, path, entry_point, surveyed_area):
    """
    Plots the geofence, the generated UAV path, and the surveyed area.
    """
    fig, ax = plt.subplots(figsize=(10, 10))
    x, y = geofence_polygon.exterior.xy
    ax.plot(x, y, label='Geofence', color='blue', linewidth=3, zorder=3)
    
    if surveyed_area and not surveyed_area.is_empty:
        if surveyed_area.geom_type in ('Polygon', 'MultiPolygon'):
            polygons = list(surveyed_area.geoms) if surveyed_area.geom_type == 'MultiPolygon' else [surveyed_area]
            for i, poly in enumerate(polygons):
                label = 'Surveyed Area' if i == 0 else ""
                x_s, y_s = poly.exterior.xy
                ax.fill(x_s, y_s, alpha=0.4, fc='lightgreen', ec='none', label=label, zorder=1)
    if path:
        path_x = [p[0] for p in path]
        path_y = [p[1] for p in path]
        ax.plot(path_x, path_y, marker='o', linestyle='-', markersize=4, color='red', label='UAV Path', zorder=4)

    ax.plot(entry_point.x, entry_point.y, marker='*', markersize=20, color='green', label='Entry Point', zorder=5)
    ax.set_title('Optimized UAV Surveillance Path')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.legend()
    ax.grid(True)
    ax.axis('equal')
    plt.show()


def generate_optimized_path(geofence_polygon, uav_start_position, overlap_percentage, sensor_width_meters):
    """
    Wrapper function to generate an optimized surveillance path.
    Returns a list of (longitude, latitude) tuples for Cesium rendering.
    
    Args:
        geofence_polygon: Shapely Polygon defining the geofence
        uav_start_position: Shapely Point with UAV starting position (lon, lat)
        overlap_percentage: Float between 0-1 for sensor overlap
        sensor_width_meters: Float for sensor footprint width in meters
    
    Returns:
        List of (longitude, latitude) tuples representing the optimized path
    """
    try:
        # Step 1: Choose best entry point and overlap
        entry_point, optimal_path, metrics, candidates, candidate_paths, best_idx = choose_best_entry_point(
            geofence_polygon, uav_start_position, overlap_percentage, sensor_width_meters
        )
        
        if not optimal_path or len(optimal_path) < 2:
            return []
        
        best_candidate = None
        for m in metrics:
            if m['corner_index'] == best_idx:
                best_candidate = m
                break
        
        # Step 2: Optimize overlap
        best_overlap, best_overlap_path, overlap_metrics, overlaps, overlap_paths, best_overlap_idx, best_overlap_short_axis = choose_best_overlap(
            geofence_polygon, entry_point, overlap_percentage, sensor_width_meters
        )
        
        if best_overlap_path and len(best_overlap_path) > 1:
            optimal_path = best_overlap_path
        
        # Step 3: Path Optimization Pipeline
        # 3.1: Coverage Barrier Pruning
        pruned_path = prune_path_by_coverage_barrier(
            optimal_path, geofence_polygon, sensor_width_meters,
            coverage_barrier_ratio=0.95,
            min_marginal_gain_ratio_per_deg=0.005,
            consecutive_steps=2,
            debug=False
        )
        if len(pruned_path) < len(optimal_path):
            optimal_path = pruned_path
        
        # 3.2: Return-Leg Pruning
        pruned_path = prune_return_with_low_gain(
            optimal_path, entry_point, geofence_polygon, sensor_width_meters,
            coverage_barrier_ratio=0.95,
            min_marginal_gain_ratio_per_deg=0.005,
            consecutive_steps=2,
            min_return_delta_deg=0.0003
        )
        if len(pruned_path) < len(optimal_path):
            optimal_path = pruned_path
        
        # 3.3: Waypoint Shortcutting
        pruned_path = shortcut_redundant_waypoints(
            optimal_path, geofence_polygon, sensor_width_meters,
            coverage_loss_threshold=0.003,
            debug=False
        )
        if len(pruned_path) < len(optimal_path):
            optimal_path = pruned_path
        
        # 3.4: Final Tail Trimming
        pruned_path = trim_redundant_tail(
            optimal_path, geofence_polygon, sensor_width_meters,
            relative_gain_threshold=0.005,
            debug=False
        )
        if len(pruned_path) < len(optimal_path):
            optimal_path = pruned_path
        
        return optimal_path
        
    except Exception as e:
        print(f"Error generating optimized path: {e}")
        return []


if __name__ == '__main__':
    KML_FILE = 'kml/path2.kml'  # KML file to process
    UAV_START_LOCATION = Point(149.1, -35.3) 
    SENSOR_WIDTH_METERS = 30
    OVERLAP_PERCENTAGE = 0.2
    
    # Test mode: disabled for production
    TEST_DIFFERENT_ENTRIES = False

    try:
        geofence_coordinates = parse_kml(KML_FILE)
        geofence = Polygon(geofence_coordinates)
        print("Successfully parsed KML file.")
    except (FileNotFoundError, ValueError, ET.ParseError) as e:
        print(f"Error: {e}")
        exit()

    if TEST_DIFFERENT_ENTRIES:
        # Try each corner to find which one produces the inefficient tail
        print("\n=== TESTING ALL CORNERS TO FIND INEFFICIENT TAIL ===")
        corners = [Point(c) for c in geofence.exterior.coords[:-1]]
        for i, corner in enumerate(corners):
            print(f"\n--- Testing Corner {i}: {corner.wkt} ---")
            test_path = generate_surveillance_path(geofence, OVERLAP_PERCENTAGE, SENSOR_WIDTH_METERS, corner, verbose=False, force_short_axis=False)
            if test_path and len(test_path) > 1:
                cov, length = compute_path_metrics(geofence, test_path, SENSOR_WIDTH_METERS)
                print(f"  Generated {len(test_path)} waypoints, coverage={cov:.3f}, length={length:.6f}")
                
                # Try pruning this path
                pruned = prune_path_by_coverage_barrier(test_path, geofence, SENSOR_WIDTH_METERS, 
                                                        coverage_barrier_ratio=0.95, min_marginal_gain_ratio_per_deg=0.005, 
                                                        consecutive_steps=2, debug=False)
                if len(pruned) < len(test_path):
                    print(f"  ✓ PRUNING WORKED: {len(test_path)} → {len(pruned)} waypoints")
        print("\n=== END CORNER TESTING ===\n")
    
    entry_point, optimal_path, metrics, candidates, candidate_paths, best_idx = choose_best_entry_point(
        geofence, UAV_START_LOCATION, OVERLAP_PERCENTAGE, SENSOR_WIDTH_METERS
    )
    print("Entry point optimization (top 3 nearest corners):")
    for m in metrics:
        axis_label = "Short" if m['short_axis'] else "Long"
        score = (m['coverage_ratio'], -m['path_length_deg'])
        print(f"  corner={m['corner_index']}, axis={axis_label}, entry=({m['entry_point'][0]:.6f},{m['entry_point'][1]:.6f}), coverage={m['coverage_ratio']:.3f}, length_deg={m['path_length_deg']:.6f}, waypoints={m['waypoints']}, score=({score[0]:.3f}, {score[1]:.6f})")
    
    best_candidate = None
    for m in metrics:
        if m['corner_index'] == best_idx:
            best_candidate = m
            break

    if best_candidate:
        best_axis_label = "Short" if best_candidate['short_axis'] else "Long"
        print(f"Chosen entry point: {entry_point.wkt} with {best_axis_label} axis (Best Score)")
    else:
        print("No valid entry point could be determined.")

    # Visualize simulated candidate paths and coverage
    try:
        plot_candidate_paths(geofence, candidates, candidate_paths, metrics, best_candidate, SENSOR_WIDTH_METERS)
    except Exception as e:
        print(f"Candidate plotting failed: {e}")

    # Optimize overlap around provided value using chosen entry point
    best_overlap, best_overlap_path, overlap_metrics, overlaps, overlap_paths, best_overlap_idx, best_overlap_short_axis = choose_best_overlap(
        geofence, entry_point, OVERLAP_PERCENTAGE, SENSOR_WIDTH_METERS
    )
    print("\nOverlap optimization around base value:")
    for m in overlap_metrics:
        axis_label = "Short" if m['short_axis'] else "Long"
        score = (m['coverage_ratio'], -m['path_length_deg'])
        print(f"  overlap={m['overlap']:.4f}, axis={axis_label}, coverage={m['coverage_ratio']:.3f}, length_deg={m['path_length_deg']:.6f}, waypoints={m['waypoints']}, score=({score[0]:.3f}, {score[1]:.6f})")
    
    best_ov_axis_label = "Short" if best_overlap_short_axis else "Long"
    print(f"Chosen overlap: {best_overlap:.4f} with {best_ov_axis_label} axis (Best Score)")

    # Use the best-overlap path as final (v1)
    if best_overlap_path and len(best_overlap_path) > 1:
        optimal_path = best_overlap_path
        
        # Show overlap candidates visualization BEFORE pruning
        try:
            plot_overlap_candidates(geofence, entry_point, overlaps, overlap_paths, overlap_metrics, best_overlap_idx, best_overlap_short_axis, SENSOR_WIDTH_METERS)
        except Exception as e:
            print(f"Overlap plotting failed: {e}")

    # Store initial path and metrics before optimization
    initial_path = list(optimal_path) if optimal_path else []
    if optimal_path and len(optimal_path) > 1:
        initial_coverage, initial_length_deg = compute_path_metrics(geofence, optimal_path, SENSOR_WIDTH_METERS)
        initial_waypoints = len(optimal_path)
        # Convert degrees to kilometers
        meters_per_degree_lat = 111320.0
        initial_length_km = initial_length_deg * meters_per_degree_lat / 1000.0
        
        print("\n--- Path Before Optimization ---")
        print(f"  Waypoints: {initial_waypoints}")
        print(f"  Coverage: {initial_coverage:.2%}")
        print(f"  Path Length: {initial_length_km:.3f} km")

    # --- Path Post-Processing ---
    # Prune the tail of the path to remove inefficient return segments
    print("\n--- Path Optimization Pipeline ---")
    
    # Step 1: Use coverage barrier pruning (removes tail after coverage threshold is reached and marginal gains are low)
    print("  Step 1: Coverage Barrier Pruning")
    pruned_path = prune_path_by_coverage_barrier(
        optimal_path, geofence, SENSOR_WIDTH_METERS,
        coverage_barrier_ratio=0.95,  # Lowered from 0.985 to 0.95 (95% coverage)
        min_marginal_gain_ratio_per_deg=0.005,  # Increased from 0.002 to 0.005 (more aggressive)
        consecutive_steps=2,  # Require 2 consecutive low-gain steps
        debug=False  # Disable debug for cleaner output
    )
    if len(pruned_path) < len(optimal_path):
        print(f"    Result: {len(optimal_path)} → {len(pruned_path)} waypoints")
        optimal_path = pruned_path
    else:
        print(f"    Result: No pruning needed")
    
    # Step 2: Prune inefficient return segments (removes tail moving back toward entry with low gain)
    print("\n  Step 2: Return-Leg Pruning")
    pruned_path = prune_return_with_low_gain(
        optimal_path, entry_point, geofence, SENSOR_WIDTH_METERS,
        coverage_barrier_ratio=0.95,  # Lowered from 0.985
        min_marginal_gain_ratio_per_deg=0.005,  # Increased from 0.003
        consecutive_steps=2,
        min_return_delta_deg=0.0003  # Lowered from 0.0005 (more sensitive)
    )
    if len(pruned_path) < len(optimal_path):
        print(f"    Result: {len(optimal_path)} → {len(pruned_path)} waypoints")
        optimal_path = pruned_path
    else:
        print(f"    Result: No pruning needed")
    
    # Step 3: Waypoint Shortcutting - skip redundant intermediate waypoints
    print("\n  Step 3: Waypoint Shortcutting")
    pruned_path = shortcut_redundant_waypoints(
        optimal_path, geofence, SENSOR_WIDTH_METERS,
        coverage_loss_threshold=0.003,  # Allow max 0.3% coverage loss (very conservative)
        debug=False
    )
    if len(pruned_path) < len(optimal_path):
        print(f"    Result: {len(optimal_path)} → {len(pruned_path)} waypoints")
        optimal_path = pruned_path
    else:
        print(f"    Result: No change")
    
    # Step 4: Final cleanup - trim any remaining redundant waypoints at the tail
    print("\n  Step 4: Final Tail Trimming")
    pruned_path = trim_redundant_tail(
        optimal_path, geofence, SENSOR_WIDTH_METERS,
        relative_gain_threshold=0.005,  # Conservative: 0.5% of total area
        debug=False
    )
    if len(pruned_path) < len(optimal_path):
        print(f"    Result: {len(optimal_path)} → {len(pruned_path)} waypoints")
        optimal_path = pruned_path
    else:
        print(f"    Result: No trimming needed")
    
    # Calculate final metrics and show comparison
    if optimal_path and len(optimal_path) > 1:
        final_coverage, final_length_deg = compute_path_metrics(geofence, optimal_path, SENSOR_WIDTH_METERS)
        final_waypoints = len(optimal_path)
        final_length_km = final_length_deg * meters_per_degree_lat / 1000.0
        
        print("\n--- Path After Optimization ---")
        print(f"  Waypoints: {final_waypoints}")
        print(f"  Coverage: {final_coverage:.2%}")
        print(f"  Path Length: {final_length_km:.3f} km")
        
        print("\n--- Optimization Results ---")
        waypoints_saved = initial_waypoints - final_waypoints
        distance_saved_km = initial_length_km - final_length_km
        distance_saved_pct = (distance_saved_km / initial_length_km * 100) if initial_length_km > 0 else 0
        coverage_change = final_coverage - initial_coverage
        
        print(f"  Waypoints reduced: {initial_waypoints} → {final_waypoints} (-{waypoints_saved})")
        print(f"  Distance saved: {distance_saved_km:.3f} km ({distance_saved_pct:.1f}%)")
        print(f"  Coverage change: {coverage_change:+.2%}")
        
        # Show before/after comparison visualization
        if initial_path and len(initial_path) > 1:
            print("\n📊 Displaying before/after optimization comparison...")
            before_metrics = (initial_waypoints, initial_coverage, initial_length_km)
            after_metrics = (final_waypoints, final_coverage, final_length_km)
            try:
                plot_optimization_comparison(geofence, initial_path, optimal_path, entry_point, 
                                            SENSOR_WIDTH_METERS, before_metrics, after_metrics)
            except Exception as e:
                print(f"Comparison plotting failed: {e}")

    # Regenerate the final path with verbose logging on
    print("\n--- Detailed Path Generation Log ---")
    print("Regenerating final path with verbose logging:")
    final_path_for_logging = generate_surveillance_path(
        geofence, best_overlap, SENSOR_WIDTH_METERS, entry_point, verbose=True, force_short_axis=best_overlap_short_axis
    )
    
    surveyed_area = None
    if optimal_path and len(optimal_path) > 1:
        flight_path_line = LineString(optimal_path)
        lat_mid = geofence.centroid.y
        meters_per_degree_lat = 111320.0
        sensor_buffer_deg = (SENSOR_WIDTH_METERS / 2.0) / meters_per_degree_lat
        surveyed_area = flight_path_line.buffer(sensor_buffer_deg, cap_style=3) # Use Square caps for better visualization

    if not optimal_path:
        print("Could not generate a valid path inside the geofence.")
    else:
        final_coverage, final_length_deg = compute_path_metrics(geofence, optimal_path, SENSOR_WIDTH_METERS)
        final_length_km = final_length_deg * 111.320  # Convert degrees to km
        
        print("\n===========================================")
        print("         FINAL PATH SUMMARY")
        print("===========================================")
        print(f"  Total Waypoints: {len(optimal_path)}")
        print(f"  Coverage: {final_coverage:.2%}")
        print(f"  Path Length: {final_length_km:.3f} km")
        print("===========================================")

        print("\nGenerated Optimal Surveillance Path Waypoints:")
        for i, waypoint in enumerate(optimal_path):
            print(f"  {i+1}: Longitude={waypoint[0]:.6f}, Latitude={waypoint[1]:.6f}")
        plot_path(geofence, optimal_path, entry_point, surveyed_area)

