from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "configs" / "gui_visual_metrics.json"
REFERENCE_OVERRIDES_PATH = ROOT / "configs" / "gui_visual_reference_overrides.json"
PREVIEW_MANIFEST_PATH = ROOT / "artifacts" / "gui-design-previews" / "preview-manifest.json"
PREVIEW_DIR = ROOT / "artifacts" / "gui-design-previews"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def main() -> int:
    errors = check_gui_visual_metrics()
    if errors:
        for error in errors:
            print(f"GUI visual metrics: {error}", file=sys.stderr)
        return 1
    metrics = load_json(METRICS_PATH)
    apply_reference_overrides(metrics)
    region_total = count_regions(metrics)
    anchor_total = count_color_anchors(metrics)
    line_anchor_total = count_line_anchors(metrics)
    topology_total = count_topology_contracts(metrics)
    print(
        "GUI visual metrics passed: "
        f"{region_total}/{region_total} regions measured, "
        f"{anchor_total}/{anchor_total} color anchors measured, "
        f"{line_anchor_total}/{line_anchor_total} line anchors measured, "
        f"{topology_total}/{topology_total} topology contracts measured"
    )
    return 0


def check_gui_visual_metrics() -> list[str]:
    try:
        metrics = load_json(METRICS_PATH)
        apply_reference_overrides(metrics)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {display(METRICS_PATH)}: {exc}"]
    try:
        manifest = load_json(PREVIEW_MANIFEST_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read {display(PREVIEW_MANIFEST_PATH)}: {exc}"]

    errors: list[str] = []
    errors.extend(check_metrics_shape(metrics))
    if errors:
        return errors
    manifest_images = preview_images_by_preset(manifest)
    state_preview_images = preview_images_by_state_preview(manifest)
    expected_size = tuple(metrics["preview_size"])
    if set(metrics["presets"]) != set(manifest_images):
        errors.append(
            f"preset visual metric ids {sorted(metrics['presets'])} must equal preview manifest ids {sorted(manifest_images)}"
        )
    errors.extend(check_metric_images("preset", metrics["presets"], manifest_images, expected_size))
    state_metrics = metrics.get("state_previews", {})
    if isinstance(state_metrics, dict):
        if set(state_metrics) != set(state_preview_images):
            errors.append(
                "state preview visual metric ids "
                f"{sorted(state_metrics)} must equal preview manifest state ids {sorted(state_preview_images)}"
            )
        errors.extend(check_metric_images("state preview", state_metrics, state_preview_images, expected_size))
    return errors


def apply_reference_overrides(metrics: dict[str, Any]) -> None:
    """Use measured layouts when a preset is reworked from an external reference."""
    if not REFERENCE_OVERRIDES_PATH.is_file():
        return
    overrides = load_json(REFERENCE_OVERRIDES_PATH)
    if overrides.get("schema_version") != 1:
        raise ValueError("GUI visual reference overrides schema_version must be 1")
    items = overrides.get("presets")
    presets = metrics.get("presets")
    if not isinstance(items, dict) or not isinstance(presets, dict):
        raise ValueError("GUI visual reference overrides presets must be an object")
    for preset_id, preset_metrics in items.items():
        if preset_id not in presets or not isinstance(preset_metrics, dict):
            raise ValueError(f"invalid GUI visual reference override: {preset_id}")
        presets[preset_id] = preset_metrics


def check_metric_images(
    collection_label: str,
    metric_items: dict[str, Any],
    manifest_images: dict[str, str],
    expected_size: tuple[int, int],
) -> list[str]:
    errors: list[str] = []
    for preset_id, preset_metrics in metric_items.items():
        image_name = manifest_images.get(preset_id)
        if image_name is None:
            errors.append(f"{collection_label} {preset_id} missing from preview manifest")
            continue
        path = PREVIEW_DIR / image_name
        if not path.is_file():
            errors.append(f"{collection_label} {preset_id} image missing: {display(path)}")
            continue
        try:
            image = read_png_rgb(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if (image.width, image.height) != expected_size:
            errors.append(f"{preset_id} PNG dimensions {(image.width, image.height)} must equal {expected_size}")
            continue
        for region in preset_metrics["regions"]:
            errors.extend(check_region(preset_id, image, region))
        for anchor in preset_metrics.get("color_anchors", []):
            errors.extend(check_color_anchor(preset_id, image, anchor))
        for anchor in preset_metrics.get("line_anchors", []):
            errors.extend(check_line_anchor(preset_id, image, anchor))
        for contract in preset_metrics.get("topology", []):
            errors.extend(check_topology_contract(preset_id, preset_metrics, contract))
    return errors


def check_metrics_shape(metrics: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if metrics.get("schema_version") != 1:
        errors.append("configs/gui_visual_metrics.json schema_version must be 1")
    if float(metrics.get("target_percent", 0)) != 100.0:
        errors.append("GUI visual metrics target_percent must be 100")
    if metrics.get("preview_size") != [1280, 760]:
        errors.append("GUI visual metrics preview_size must be [1280, 760]")
    presets = metrics.get("presets")
    if not isinstance(presets, dict) or not presets:
        return [*errors, "GUI visual metrics presets must be a non-empty object"]
    errors.extend(check_metrics_collection_shape("preset", presets))
    state_previews = metrics.get("state_previews", {})
    if not isinstance(state_previews, dict):
        errors.append("GUI visual metrics state_previews must be an object when present")
    else:
        errors.extend(check_metrics_collection_shape("state preview", state_previews))
    return errors


def check_metrics_collection_shape(collection_label: str, collection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for preset_id, preset_metrics in collection.items():
        if not isinstance(preset_metrics, dict):
            errors.append(f"{collection_label} {preset_id} metrics must be an object")
            continue
        regions = preset_metrics.get("regions")
        if not isinstance(regions, list) or not regions:
            errors.append(f"{collection_label} {preset_id} metrics must include non-empty regions")
            continue
        seen: set[str] = set()
        for region in regions:
            if not isinstance(region, dict):
                errors.append(f"{preset_id} region must be an object")
                continue
            region_id = str(region.get("id", ""))
            if not region_id:
                errors.append(f"{preset_id} region missing id")
            if region_id in seen:
                errors.append(f"{preset_id} duplicate region id: {region_id}")
            seen.add(region_id)
            if not valid_box(region.get("box")):
                errors.append(f"{preset_id}.{region_id} box must be [left, top, right, bottom] inside the preview")
            bounds = region.get("mean_luminance")
            if not (
                isinstance(bounds, list)
                and len(bounds) == 2
                and all(isinstance(item, int | float) for item in bounds)
                and 0 <= bounds[0] <= bounds[1] <= 255
            ):
                errors.append(f"{preset_id}.{region_id} mean_luminance must be [min, max] between 0 and 255")
            min_unique = region.get("min_unique_colors")
            if not isinstance(min_unique, int) or min_unique < 1:
                errors.append(f"{preset_id}.{region_id} min_unique_colors must be a positive integer")
        topology = preset_metrics.get("topology", [])
        if not isinstance(topology, list):
            errors.append(f"{preset_id} topology must be a list when present")
            continue
        seen_topology: set[str] = set()
        for contract in topology:
            if not isinstance(contract, dict):
                errors.append(f"{preset_id} topology contract must be an object")
                continue
            contract_id = str(contract.get("id", ""))
            if not contract_id:
                errors.append(f"{preset_id} topology contract missing id")
            if contract_id in seen_topology:
                errors.append(f"{preset_id} duplicate topology contract id: {contract_id}")
            seen_topology.add(contract_id)
            first = contract.get("from")
            second = contract.get("to")
            if not isinstance(first, str) or first not in seen:
                errors.append(f"{preset_id}.{contract_id} from must reference a known region id")
            if not isinstance(second, str) or second not in seen:
                errors.append(f"{preset_id}.{contract_id} to must reference a known region id")
            relation = contract.get("relation")
            if relation not in {"left_of", "right_of", "above", "below", "inside", "contains", "overlaps_x", "overlaps_y"}:
                errors.append(f"{preset_id}.{contract_id} relation is unsupported: {relation!r}")
            for key in ["min_gap", "max_gap", "min_overlap"]:
                if key in contract and (not isinstance(contract[key], int) or int(contract[key]) < 0):
                    errors.append(f"{preset_id}.{contract_id} {key} must be a non-negative integer")
        color_anchors = preset_metrics.get("color_anchors", [])
        if not isinstance(color_anchors, list):
            errors.append(f"{preset_id} color_anchors must be a list when present")
            continue
        seen_anchors: set[str] = set()
        for anchor in color_anchors:
            if not isinstance(anchor, dict):
                errors.append(f"{preset_id} color anchor must be an object")
                continue
            anchor_id = str(anchor.get("id", ""))
            if not anchor_id:
                errors.append(f"{preset_id} color anchor missing id")
            if anchor_id in seen_anchors:
                errors.append(f"{preset_id} duplicate color anchor id: {anchor_id}")
            seen_anchors.add(anchor_id)
            if not valid_point(anchor.get("point")):
                errors.append(f"{preset_id}.{anchor_id} point must be [x, y] inside the preview")
            minimum = anchor.get("rgb_min")
            maximum = anchor.get("rgb_max")
            if not valid_rgb_bounds(minimum, maximum):
                errors.append(f"{preset_id}.{anchor_id} rgb_min/rgb_max must be RGB channel bounds")
        line_anchors = preset_metrics.get("line_anchors", [])
        if not isinstance(line_anchors, list):
            errors.append(f"{preset_id} line_anchors must be a list when present")
            continue
        seen_lines: set[str] = set()
        for anchor in line_anchors:
            if not isinstance(anchor, dict):
                errors.append(f"{preset_id} line anchor must be an object")
                continue
            anchor_id = str(anchor.get("id", ""))
            if not anchor_id:
                errors.append(f"{preset_id} line anchor missing id")
            if anchor_id in seen_lines:
                errors.append(f"{preset_id} duplicate line anchor id: {anchor_id}")
            seen_lines.add(anchor_id)
            start = anchor.get("from")
            end = anchor.get("to")
            if not valid_point(start) or not valid_point(end):
                errors.append(f"{preset_id}.{anchor_id} from/to must be [x, y] points inside the preview")
            elif start[0] != end[0] and start[1] != end[1]:
                errors.append(f"{preset_id}.{anchor_id} must be horizontal or vertical")
            minimum = anchor.get("rgb_min")
            maximum = anchor.get("rgb_max")
            if not valid_rgb_bounds(minimum, maximum):
                errors.append(f"{preset_id}.{anchor_id} rgb_min/rgb_max must be RGB channel bounds")
            ratio = anchor.get("min_match_ratio")
            if not isinstance(ratio, int | float) or not 0 < float(ratio) <= 1:
                errors.append(f"{preset_id}.{anchor_id} min_match_ratio must be between 0 and 1")
    return errors


def valid_point(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 2 or not all(isinstance(item, int) for item in value):
        return False
    x, y = value
    return 0 <= x < 1280 and 0 <= y < 760


def valid_rgb_bounds(minimum: Any, maximum: Any) -> bool:
    if (
        not isinstance(minimum, list)
        or not isinstance(maximum, list)
        or len(minimum) != 3
        or len(maximum) != 3
        or not all(isinstance(item, int | float) for item in [*minimum, *maximum])
    ):
        return False
    return all(0 <= minimum[index] <= maximum[index] <= 255 for index in range(3))


def valid_box(value: Any) -> bool:
    if not isinstance(value, list) or len(value) != 4 or not all(isinstance(item, int) for item in value):
        return False
    left, top, right, bottom = value
    return 0 <= left < right <= 1280 and 0 <= top < bottom <= 760


def preview_images_by_preset(manifest: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    presets = manifest.get("presets", [])
    if not isinstance(presets, list):
        return result
    for item in presets:
        if not isinstance(item, dict):
            continue
        image = item.get("image")
        if not isinstance(image, dict):
            continue
        result[str(item.get("id", ""))] = str(image.get("path", ""))
    return result


def preview_images_by_state_preview(manifest: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    state_previews = manifest.get("state_previews", [])
    if not isinstance(state_previews, list):
        return result
    for item in state_previews:
        if not isinstance(item, dict):
            continue
        image = item.get("image")
        if not isinstance(image, dict):
            continue
        result[str(item.get("id", ""))] = str(image.get("path", ""))
    return result


def check_region(preset_id: str, image: PngImage, region: dict[str, Any]) -> list[str]:
    region_id = str(region["id"])
    pixels = list(region_pixels(image, tuple(region["box"])))
    if not pixels:
        return [f"{preset_id}.{region_id} has no pixels"]
    mean_luminance = sum(luminance(pixel) for pixel in pixels) / len(pixels)
    minimum, maximum = region["mean_luminance"]
    errors: list[str] = []
    if not minimum <= mean_luminance <= maximum:
        errors.append(
            f"{preset_id}.{region_id} mean luminance {mean_luminance:.1f} outside expected {minimum:.1f}-{maximum:.1f}"
        )
    unique_colors = len(set(pixels))
    min_unique = int(region["min_unique_colors"])
    if unique_colors < min_unique:
        errors.append(f"{preset_id}.{region_id} unique colors {unique_colors} below expected {min_unique}")
    return errors


def check_color_anchor(preset_id: str, image: PngImage, anchor: dict[str, Any]) -> list[str]:
    anchor_id = str(anchor["id"])
    x, y = anchor["point"]
    pixel = image.pixels[y * image.width + x]
    minimum = anchor["rgb_min"]
    maximum = anchor["rgb_max"]
    for channel_index, channel_name in enumerate(["red", "green", "blue"]):
        if not minimum[channel_index] <= pixel[channel_index] <= maximum[channel_index]:
            return [
                (
                    f"{preset_id}.{anchor_id} {channel_name} channel {pixel[channel_index]} outside "
                    f"expected {minimum[channel_index]}-{maximum[channel_index]} at {x},{y}; "
                    f"sampled RGB={pixel}"
                )
            ]
    return []


def check_line_anchor(preset_id: str, image: PngImage, anchor: dict[str, Any]) -> list[str]:
    anchor_id = str(anchor["id"])
    pixels = [image.pixels[y * image.width + x] for x, y in line_points(anchor["from"], anchor["to"])]
    minimum = anchor["rgb_min"]
    maximum = anchor["rgb_max"]
    matches = sum(1 for pixel in pixels if rgb_in_bounds(pixel, minimum, maximum))
    ratio = matches / len(pixels)
    expected = float(anchor["min_match_ratio"])
    if ratio < expected:
        return [
            (
                f"{preset_id}.{anchor_id} match ratio {ratio:.3f} below expected {expected:.3f}; "
                f"{matches}/{len(pixels)} pixels matched RGB bounds {minimum}-{maximum}"
            )
        ]
    return []


def check_topology_contract(
    preset_id: str,
    preset_metrics: dict[str, Any],
    contract: dict[str, Any],
) -> list[str]:
    contract_id = str(contract["id"])
    boxes = region_boxes(preset_metrics)
    first = boxes[str(contract["from"])]
    second = boxes[str(contract["to"])]
    relation = str(contract["relation"])
    if relation == "left_of":
        return check_gap_contract(preset_id, contract_id, contract, first[2], second[0], relation)
    if relation == "right_of":
        return check_gap_contract(preset_id, contract_id, contract, second[2], first[0], relation)
    if relation == "above":
        return check_gap_contract(preset_id, contract_id, contract, first[3], second[1], relation)
    if relation == "below":
        return check_gap_contract(preset_id, contract_id, contract, second[3], first[1], relation)
    if relation == "inside":
        if first[0] < second[0] or first[1] < second[1] or first[2] > second[2] or first[3] > second[3]:
            return [f"{preset_id}.{contract_id} expected {contract['from']} inside {contract['to']}"]
        return []
    if relation == "contains":
        if second[0] < first[0] or second[1] < first[1] or second[2] > first[2] or second[3] > first[3]:
            return [f"{preset_id}.{contract_id} expected {contract['from']} to contain {contract['to']}"]
        return []
    if relation == "overlaps_x":
        overlap = min(first[2], second[2]) - max(first[0], second[0])
        return check_overlap_contract(preset_id, contract_id, contract, overlap, relation)
    if relation == "overlaps_y":
        overlap = min(first[3], second[3]) - max(first[1], second[1])
        return check_overlap_contract(preset_id, contract_id, contract, overlap, relation)
    return [f"{preset_id}.{contract_id} has unsupported topology relation: {relation}"]


def check_gap_contract(
    preset_id: str,
    contract_id: str,
    contract: dict[str, Any],
    first_edge: int,
    second_edge: int,
    relation: str,
) -> list[str]:
    gap = second_edge - first_edge
    if gap < int(contract.get("min_gap", 0)):
        return [f"{preset_id}.{contract_id} {relation} gap {gap} below expected {contract.get('min_gap', 0)}"]
    max_gap = contract.get("max_gap")
    if isinstance(max_gap, int) and gap > max_gap:
        return [f"{preset_id}.{contract_id} {relation} gap {gap} above expected {max_gap}"]
    return []


def check_overlap_contract(
    preset_id: str,
    contract_id: str,
    contract: dict[str, Any],
    overlap: int,
    relation: str,
) -> list[str]:
    expected = int(contract.get("min_overlap", 1))
    if overlap < expected:
        return [f"{preset_id}.{contract_id} {relation} overlap {overlap} below expected {expected}"]
    return []


def region_boxes(preset_metrics: dict[str, Any]) -> dict[str, tuple[int, int, int, int]]:
    return {str(region["id"]): tuple(region["box"]) for region in preset_metrics["regions"]}


def line_points(start: list[int], end: list[int]) -> list[tuple[int, int]]:
    x1, y1 = start
    x2, y2 = end
    if x1 == x2:
        low, high = sorted([y1, y2])
        return [(x1, y) for y in range(low, high + 1)]
    low, high = sorted([x1, x2])
    return [(x, y1) for x in range(low, high + 1)]


def rgb_in_bounds(pixel: tuple[int, int, int], minimum: list[int], maximum: list[int]) -> bool:
    return all(minimum[index] <= pixel[index] <= maximum[index] for index in range(3))


class PngImage:
    def __init__(self, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
        self.width = width
        self.height = height
        self.pixels = pixels


def read_png_rgb(path: Path) -> PngImage:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"not a PNG file: {display(path)}")
    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    compressed = bytearray()
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", chunk_data)
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width is None or height is None or bit_depth is None or color_type is None or interlace is None:
        raise ValueError(f"PNG missing IHDR: {display(path)}")
    if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
        raise ValueError(
            f"unsupported PNG format for {display(path)}: bit_depth={bit_depth}, color_type={color_type}, interlace={interlace}"
        )
    channels = 3 if color_type == 2 else 4
    row_size = width * channels
    raw = zlib.decompress(bytes(compressed))
    rows: list[bytes] = []
    index = 0
    previous = bytes(row_size)
    for _row in range(height):
        if index >= len(raw):
            raise ValueError(f"PNG data ended early: {display(path)}")
        filter_type = raw[index]
        index += 1
        row = bytearray(raw[index : index + row_size])
        index += row_size
        unfilter_scanline(row, previous, channels, filter_type)
        rows.append(bytes(row))
        previous = rows[-1]
    pixels: list[tuple[int, int, int]] = []
    for row in rows:
        for col in range(0, row_size, channels):
            pixels.append((row[col], row[col + 1], row[col + 2]))
    return PngImage(width, height, pixels)


def unfilter_scanline(row: bytearray, previous: bytes, bpp: int, filter_type: int) -> None:
    if filter_type == 0:
        return
    if filter_type == 1:
        for index, value in enumerate(row):
            left = row[index - bpp] if index >= bpp else 0
            row[index] = (value + left) & 0xFF
        return
    if filter_type == 2:
        for index, value in enumerate(row):
            row[index] = (value + previous[index]) & 0xFF
        return
    if filter_type == 3:
        for index, value in enumerate(row):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            row[index] = (value + ((left + up) // 2)) & 0xFF
        return
    if filter_type == 4:
        for index, value in enumerate(row):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            row[index] = (value + paeth(left, up, upper_left)) & 0xFF
        return
    raise ValueError(f"unsupported PNG filter type: {filter_type}")


def paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def region_pixels(image: PngImage, box: tuple[int, int, int, int]):
    left, top, right, bottom = box
    for y in range(top, bottom):
        row_offset = y * image.width
        for x in range(left, right):
            yield image.pixels[row_offset + x]


def luminance(pixel: tuple[int, int, int]) -> float:
    red, green, blue = pixel
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def count_regions(metrics: dict[str, Any]) -> int:
    return count_metric_items(metrics, "regions")


def count_color_anchors(metrics: dict[str, Any]) -> int:
    return count_metric_items(metrics, "color_anchors")


def count_line_anchors(metrics: dict[str, Any]) -> int:
    return count_metric_items(metrics, "line_anchors")


def count_topology_contracts(metrics: dict[str, Any]) -> int:
    return count_metric_items(metrics, "topology")


def count_metric_items(metrics: dict[str, Any], metric_key: str) -> int:
    total = 0
    for collection_key in ("presets", "state_previews"):
        collection = metrics.get(collection_key, {})
        if not isinstance(collection, dict):
            continue
        total += sum(len(item.get(metric_key, [])) for item in collection.values() if isinstance(item, dict))
    return total


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{display(path)} must contain a JSON object")
    return data


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
