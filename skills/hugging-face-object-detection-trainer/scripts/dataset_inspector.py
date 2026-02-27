#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Dataset Format Inspector for Object Detection Training

Inspects Hugging Face datasets to determine object detection training compatibility.
Uses Datasets Server API for instant results - no dataset download needed!

ULTRA-EFFICIENT: Uses HF Datasets Server API - completes in <2 seconds.

Usage with HF Jobs:
    hf_jobs("uv", {
        "script": "path/to/dataset_inspector.py",
        "script_args": ["--dataset", "your/dataset", "--split", "train"]
    })
"""

import argparse
import sys
import json
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Tuple


def parse_args():
    parser = argparse.ArgumentParser(description="Inspect dataset format for object detection training")
    parser.add_argument("--dataset", type=str, required=True, help="Dataset name")
    parser.add_argument("--split", type=str, default="train", help="Dataset split (default: train)")
    parser.add_argument("--config", type=str, default="default", help="Dataset config name (default: default)")
    parser.add_argument("--preview", type=int, default=150, help="Max chars per field preview")
    parser.add_argument("--samples", type=int, default=5, help="Number of samples to fetch (default: 5)")
    parser.add_argument("--json-output", action="store_true", help="Output as JSON")
    return parser.parse_args()


def api_request(url: str) -> Dict:
    """Make API request to Datasets Server"""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Exception(f"API request failed: {e.code} {e.reason}")
    except Exception as e:
        raise Exception(f"API request failed: {str(e)}")


def get_splits(dataset: str) -> Dict:
    """Get available splits for dataset"""
    url = f"https://datasets-server.huggingface.co/splits?dataset={urllib.parse.quote(dataset)}"
    return api_request(url)


def get_rows(dataset: str, config: str, split: str, offset: int = 0, length: int = 5) -> Dict:
    """Get rows from dataset"""
    url = f"https://datasets-server.huggingface.co/rows?dataset={urllib.parse.quote(dataset)}&config={config}&split={split}&offset={offset}&length={length}"
    return api_request(url)


def find_columns(columns: List[str], patterns: List[str]) -> List[str]:
    """Find columns matching patterns"""
    return [c for c in columns if any(p in c.lower() for p in patterns)]


def detect_bbox_format(bbox: List[float], image_size: Tuple[int, int] = None) -> str:
    """
    Detect bounding box format based on values and optionally image dimensions.
    Common formats:
    - [x_min, y_min, x_max, y_max] - XYXY (Pascal VOC)
    - [x_min, y_min, width, height] - XYWH (COCO)
    - [x_center, y_center, width, height] - CXCYWH (YOLO normalized)
    """
    if len(bbox) != 4:
        return "unknown (not 4 values)"

    a, b, c, d = bbox

    is_normalized = all(0 <= v <= 1 for v in bbox)

    if c < a or d < b:
        if is_normalized:
            return "xywh_normalized"
        return "xywh (COCO style)"

    # c > a and d > b — ambiguous between xyxy and xywh.
    # Use image dimensions to disambiguate when available.
    if image_size is not None:
        img_w, img_h = image_size
        # If interpreting as xywh, right edge = a + c; if that overshoots the
        # image while c alone fits, the format is more likely xyxy.
        xywh_exceeds = (a + c > img_w * 1.05) or (b + d > img_h * 1.05)
        xyxy_exceeds = (c > img_w * 1.05) or (d > img_h * 1.05)
        if xywh_exceeds and not xyxy_exceeds:
            return "xyxy (Pascal VOC style)"
        if xyxy_exceeds and not xywh_exceeds:
            return "xywh (COCO style)"

    if is_normalized:
        return "xyxy_normalized"
    return "xyxy (Pascal VOC style)"


def _extract_image_size(row: Dict) -> Tuple[int, int] | None:
    """Try to extract (width, height) from the image column returned by Datasets Server."""
    for col in ("image", "img", "picture", "photo"):
        img = row.get(col)
        if isinstance(img, dict):
            w = img.get("width")
            h = img.get("height")
            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                return (int(w), int(h))
    return None


def analyze_annotations(sample_rows: List[Dict], annotation_cols: List[str]) -> Dict[str, Any]:
    """Analyze annotation structure from sample rows"""
    if not annotation_cols:
        return {"found": False}

    annotation_col = annotation_cols[0]
    annotations_info = {
        "found": True,
        "column": annotation_col,
        "sample_structures": [],
        "bbox_formats": [],
        "categories_found": [],
        "avg_objects_per_image": 0,
        "max_objects": 0,
        "min_objects": float('inf'),
    }

    total_objects = 0
    valid_samples = 0

    for row in sample_rows:
        ann = row["row"].get(annotation_col)
        if not ann:
            continue

        valid_samples += 1
        image_size = _extract_image_size(row["row"])

        # Check if it's a list of annotations or a dict
        if isinstance(ann, dict):
            # COCO-style or structured annotation
            sample_structure = {
                "type": "dict",
                "keys": list(ann.keys())
            }

            # Check for bounding boxes
            if "bbox" in ann or "bboxes" in ann:
                bbox_key = "bbox" if "bbox" in ann else "bboxes"
                bboxes = ann[bbox_key]
                if isinstance(bboxes, list) and len(bboxes) > 0:
                    if isinstance(bboxes[0], list):
                        # Multiple bboxes
                        num_objects = len(bboxes)
                        total_objects += num_objects
                        annotations_info["max_objects"] = max(annotations_info["max_objects"], num_objects)
                        annotations_info["min_objects"] = min(annotations_info["min_objects"], num_objects)

                        # Analyze first bbox format
                        bbox_format = detect_bbox_format(bboxes[0], image_size)
                        annotations_info["bbox_formats"].append(bbox_format)
                    else:
                        # Single bbox
                        total_objects += 1
                        annotations_info["max_objects"] = max(annotations_info["max_objects"], 1)
                        annotations_info["min_objects"] = min(annotations_info["min_objects"], 1)
                        bbox_format = detect_bbox_format(bboxes, image_size)
                        annotations_info["bbox_formats"].append(bbox_format)

            # Check for categories/classes
            for key in ["category", "categories", "label", "labels", "class", "classes", "category_id"]:
                if key in ann:
                    cats = ann[key]
                    if isinstance(cats, list):
                        annotations_info["categories_found"].extend([str(c) for c in cats])
                    else:
                        annotations_info["categories_found"].append(str(cats))

            annotations_info["sample_structures"].append(sample_structure)

        elif isinstance(ann, list):
            # List of annotation dicts
            sample_structure = {
                "type": "list",
                "length": len(ann),
                "item_type": type(ann[0]).__name__ if ann else None
            }

            if ann and isinstance(ann[0], dict):
                sample_structure["item_keys"] = list(ann[0].keys())

                # Count objects
                num_objects = len(ann)
                total_objects += num_objects
                annotations_info["max_objects"] = max(annotations_info["max_objects"], num_objects)
                annotations_info["min_objects"] = min(annotations_info["min_objects"], num_objects)

                # Check first annotation
                first_ann = ann[0]
                if "bbox" in first_ann:
                    bbox_format = detect_bbox_format(first_ann["bbox"], image_size)
                    annotations_info["bbox_formats"].append(bbox_format)

                # Check for categories
                for key in ["category", "label", "class", "category_id"]:
                    if key in first_ann:
                        for item in ann:
                            if key in item:
                                annotations_info["categories_found"].append(str(item[key]))

            annotations_info["sample_structures"].append(sample_structure)

    if valid_samples > 0:
        annotations_info["avg_objects_per_image"] = round(total_objects / valid_samples, 2)

    if annotations_info["min_objects"] == float('inf'):
        annotations_info["min_objects"] = 0

    # Get unique categories
    annotations_info["categories_found"] = list(set(annotations_info["categories_found"]))
    annotations_info["num_classes"] = len(annotations_info["categories_found"])

    # Get most common bbox format
    if annotations_info["bbox_formats"]:
        from collections import Counter
        format_counts = Counter(annotations_info["bbox_formats"])
        annotations_info["primary_bbox_format"] = format_counts.most_common(1)[0][0]

    return annotations_info


def check_object_detection_compatibility(columns: List[str], sample_rows: List[Dict]) -> Dict[str, Any]:
    """Check object detection dataset compatibility"""

    # Find image column
    image_cols = find_columns(columns, ["image", "img", "picture", "photo"])
    has_image = len(image_cols) > 0

    # Find annotation columns
    annotation_cols = find_columns(columns, ["objects", "annotations", "ann", "bbox", "bboxes", "detection"])
    has_annotations = len(annotation_cols) > 0

    # Analyze annotations
    annotations_info = analyze_annotations(sample_rows, annotation_cols) if has_annotations else {"found": False}

    # Check for separate bbox and category columns
    bbox_cols = find_columns(columns, ["bbox", "bboxes", "boxes"])
    category_cols = find_columns(columns, ["category", "label", "class", "categories", "labels", "classes"])

    # Determine readiness
    ready = has_image and (has_annotations or (len(bbox_cols) > 0 and len(category_cols) > 0))

    return {
        "ready": ready,
        "has_image": has_image,
        "image_columns": image_cols,
        "has_annotations": has_annotations,
        "annotation_columns": annotation_cols,
        "separate_bbox_columns": bbox_cols,
        "separate_category_columns": category_cols,
        "annotations_info": annotations_info,
    }


def generate_mapping_code(info: Dict[str, Any]) -> str:
    """Generate mapping code if needed"""
    if info["ready"]:
        ann_info = info["annotations_info"]
        if not ann_info.get("found"):
            return None

        # Check if format conversion is needed
        ann_col = ann_info.get("column")
        bbox_format = ann_info.get("primary_bbox_format", "unknown")

        if "coco" in bbox_format.lower() or "xywh" in bbox_format.lower():
            # Already COCO format
            return f"""# Dataset appears to be in COCO format (xywh)
# Image column: {info['image_columns'][0] if info['image_columns'] else 'image'}
# Annotation column: {ann_col}
# Use directly with transformers object detection models"""
        elif "xyxy" in bbox_format.lower():
            # Need to convert from XYXY to XYWH
            return f"""# Convert from XYXY (Pascal VOC) to XYWH (COCO) format
def convert_to_coco_format(example):
    annotations = example['{ann_col}']
    if isinstance(annotations, list):
        for ann in annotations:
            if 'bbox' in ann:
                x_min, y_min, x_max, y_max = ann['bbox']
                ann['bbox'] = [x_min, y_min, x_max - x_min, y_max - y_min]
    elif isinstance(annotations, dict) and 'bbox' in annotations:
        bbox = annotations['bbox']
        if isinstance(bbox, list) and len(bbox) > 0 and isinstance(bbox[0], list):
            for i, box in enumerate(bbox):
                x_min, y_min, x_max, y_max = box
                bbox[i] = [x_min, y_min, x_max - x_min, y_max - y_min]
    return example

dataset = dataset.map(convert_to_coco_format)"""

    elif not info["ready"]:
        # Need to create annotations structure
        if info["separate_bbox_columns"] and info["separate_category_columns"]:
            bbox_col = info["separate_bbox_columns"][0]
            cat_col = info["separate_category_columns"][0]

            return f"""# Combine separate bbox and category columns
def create_annotations(example):
    bboxes = example['{bbox_col}']
    categories = example['{cat_col}']

    if not isinstance(bboxes, list):
        bboxes = [bboxes]
    if not isinstance(categories, list):
        categories = [categories]

    annotations = []
    for bbox, cat in zip(bboxes, categories):
        annotations.append({{'bbox': bbox, 'category': cat}})

    example['objects'] = annotations
    return example

dataset = dataset.map(create_annotations)"""

    return None


def format_value_preview(value: Any, max_chars: int) -> str:
    """Format value for preview"""
    if value is None:
        return "None"
    elif isinstance(value, str):
        return value[:max_chars] + ("..." if len(value) > max_chars else "")
    elif isinstance(value, dict):
        keys = list(value.keys())
        return f"{{dict with {len(keys)} keys: {', '.join(keys[:5])}}}"
    elif isinstance(value, list):
        if len(value) == 0:
            return "[]"
        elif isinstance(value[0], dict):
            return f"[{len(value)} items] First item keys: {list(value[0].keys())}"
        elif isinstance(value[0], list):
            return f"[{len(value)} items] First item: {value[0]}"
        else:
            preview = str(value)
            return preview[:max_chars] + ("..." if len(preview) > max_chars else "")
    else:
        preview = str(value)
        return preview[:max_chars] + ("..." if len(preview) > max_chars else "")


def main():
    args = parse_args()

    print(f"Fetching dataset info via Datasets Server API...")

    try:
        # Get splits info
        splits_data = get_splits(args.dataset)
        if not splits_data or "splits" not in splits_data:
            print(f"ERROR: Could not fetch splits for dataset '{args.dataset}'")
            print(f"       Dataset may not exist or is not accessible via Datasets Server API")
            sys.exit(1)

        # Find the right config
        available_configs = set()
        split_found = False
        config_to_use = args.config

        for split_info in splits_data["splits"]:
            available_configs.add(split_info["config"])
            if split_info["config"] == args.config and split_info["split"] == args.split:
                split_found = True

        # If default config not found, try first available
        if not split_found and available_configs:
            config_to_use = list(available_configs)[0]
            print(f"Config '{args.config}' not found, trying '{config_to_use}'...")

        # Get rows
        rows_data = get_rows(args.dataset, config_to_use, args.split, offset=0, length=args.samples)

        if not rows_data or "rows" not in rows_data:
            print(f"ERROR: Could not fetch rows for dataset '{args.dataset}'")
            print(f"       Split '{args.split}' may not exist")
            print(f"       Available configs: {', '.join(sorted(available_configs))}")
            sys.exit(1)

        rows = rows_data["rows"]
        if not rows:
            print(f"ERROR: No rows found in split '{args.split}'")
            sys.exit(1)

        # Extract column info from first row
        first_row = rows[0]["row"]
        columns = list(first_row.keys())
        features = rows_data.get("features", [])

        # Get total count if available
        total_examples = "Unknown"
        for split_info in splits_data["splits"]:
            if split_info["config"] == config_to_use and split_info["split"] == args.split:
                total_examples = f"{split_info.get('num_examples', 'Unknown'):,}" if isinstance(split_info.get('num_examples'), int) else "Unknown"
                break

    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

    # Run compatibility checks
    od_info = check_object_detection_compatibility(columns, rows)

    # JSON output mode
    if args.json_output:
        result = {
            "dataset": args.dataset,
            "config": config_to_use,
            "split": args.split,
            "total_examples": total_examples,
            "columns": columns,
            "features": [{"name": f["name"], "type": f["type"]} for f in features] if features else [],
            "object_detection_compatibility": od_info,
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # Human-readable output optimized for LLM parsing
    print("=" * 80)
    print(f"OBJECT DETECTION DATASET INSPECTION")
    print("=" * 80)

    print(f"\nDataset: {args.dataset}")
    print(f"Config: {config_to_use}")
    print(f"Split: {args.split}")
    print(f"Total examples: {total_examples}")
    print(f"Samples fetched: {len(rows)}")

    print(f"\n{'COLUMNS':-<80}")
    if features:
        for feature in features:
            print(f"  {feature['name']}: {feature['type']}")
    else:
        for col in columns:
            print(f"  {col}: (type info not available)")

    print(f"\n{'EXAMPLE DATA':-<80}")
    example = first_row
    for col in columns:
        value = example.get(col)
        display = format_value_preview(value, args.preview)
        print(f"\n{col}:")
        print(f"  {display}")

    print(f"\n{'OBJECT DETECTION COMPATIBILITY':-<80}")

    print(f"\n[STATUS] {'✓ READY' if od_info['ready'] else '✗ NEEDS FORMATTING'}")

    print(f"\nImage Column:")
    if od_info["has_image"]:
        print(f"  ✓ Found: {', '.join(od_info['image_columns'])}")
    else:
        print(f"  ✗ No image column detected")
        print(f"  Expected column names: 'image', 'img', 'picture', 'photo'")

    print(f"\nAnnotations:")
    if od_info["has_annotations"]:
        print(f"  ✓ Found: {', '.join(od_info['annotation_columns'])}")
        ann_info = od_info["annotations_info"]
        if ann_info.get("found"):
            print(f"\n  Annotation Details:")
            print(f"    • Column: {ann_info['column']}")
            if ann_info.get("primary_bbox_format"):
                print(f"    • BBox Format: {ann_info['primary_bbox_format']}")
            if ann_info.get("num_classes", 0) > 0:
                print(f"    • Number of Classes: {ann_info['num_classes']}")
                print(f"    • Classes: {', '.join(ann_info['categories_found'][:10])}")
                if len(ann_info['categories_found']) > 10:
                    print(f"      (showing first 10 of {len(ann_info['categories_found'])})")
            print(f"    • Avg Objects/Image: {ann_info['avg_objects_per_image']}")
            print(f"    • Min Objects: {ann_info['min_objects']}")
            print(f"    • Max Objects: {ann_info['max_objects']}")
    elif od_info["separate_bbox_columns"] and od_info["separate_category_columns"]:
        print(f"  ⚠ Separate bbox and category columns found:")
        print(f"    BBox columns: {', '.join(od_info['separate_bbox_columns'])}")
        print(f"    Category columns: {', '.join(od_info['separate_category_columns'])}")
        print(f"  Action: These need to be combined (see mapping code below)")
    else:
        print(f"  ✗ No annotation columns detected")
        print(f"  Expected: 'objects', 'annotations', 'bbox'/'bboxes' + 'category'/'label'")

    # Mapping code
    mapping_code = generate_mapping_code(od_info)

    if mapping_code:
        print(f"\n{'PREPROCESSING CODE':-<80}")
        print(mapping_code)
    elif od_info["ready"]:
        print(f"\n{'PREPROCESSING CODE':-<80}")
        print("\n✓ Dataset is ready for object detection training!")
        print("  No preprocessing needed.")
    else:
        print(f"\n{'PREPROCESSING CODE':-<80}")
        print("\n⚠ Cannot generate automatic mapping code.")
        print("  Manual inspection and formatting required.")

    print(f"\n{'SUMMARY':-<80}")
    if od_info["ready"]:
        print(f"✓ Dataset is compatible with object detection training")
        ann_info = od_info["annotations_info"]
        if ann_info.get("primary_bbox_format"):
            print(f"  BBox format: {ann_info['primary_bbox_format']}")
        if ann_info.get("num_classes", 0) > 0:
            print(f"  Classes: {ann_info['num_classes']}")
    else:
        print(f"✗ Dataset needs formatting before use")
        if not od_info["has_image"]:
            print(f"  - Missing image column")
        if not od_info["has_annotations"]:
            print(f"  - Missing or incompatible annotation format")

    print(f"\nNote: Used Datasets Server API (instant, no download required)")

    print("\n" + "=" * 80)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
