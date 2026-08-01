#!/usr/bin/env python3
"""
export_tensorrt.py
===================
Converts a trained YOLOv8 (.pt) weights file into a TensorRT engine
suitable for real-time inference on the NVIDIA Jetson Nano.

Standard PyTorch (.pt) inference is too slow for HOLO-PATROL's onboard
DeepStream pipeline (see docs/behavior_analysis.md — the project's
operational budget is under 200 ms/frame). This script performs the
export step that bridges a trained model to the DeepStream `nvinfer`
element, which expects a pre-built TensorRT engine referenced by
`model-engine-file` inside `config_infer_primary_yoloV8.txt`
(see docs/software_setup.md, Section 3).

USAGE
-----
Run directly on the target Jetson device. TensorRT engines are
hardware- and TensorRT-version-specific and are NOT portable across
devices or JetPack versions — an engine built on a workstation GPU
will not run on the Jetson Nano, and vice versa.

    python3 scripts/export_tensorrt.py \\
        --weights weights/yolov8n_holo_patrol.pt \\
        --imgsz 640 \\
        --half \\
        --workspace 4 \\
        --device 0 \\
        --batch 1 \\
        --output engines/

After export, point `model-engine-file` in
`config_infer_primary_yoloV8.txt` at the generated `.engine` file and
restart the DeepStream pipeline (`yaw_tracker.py` / `visual_tracker_3d.py`).

REQUIREMENTS
------------
- `ultralytics` (pip install ultralytics)
- A working CUDA + TensorRT installation matching the target device
  (JetPack's bundled TensorRT on the Jetson Nano itself, or a matching
  desktop CUDA/TensorRT stack if cross-building is supported by your
  TensorRT version).

This script is intentionally NOT part of the automated test suite —
it requires GPU/TensorRT hardware and is meant to be run manually as
part of the model deployment workflow, not in CI.
"""
import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a YOLOv8 .pt model to a TensorRT engine for onboard "
            "DeepStream inference on the HOLO-PATROL Jetson Nano pipeline."
        )
    )
    parser.add_argument(
        "--weights", type=Path, required=True,
        help="Path to the trained YOLOv8 .pt weights file.",
    )
    parser.add_argument(
        "--imgsz", type=int, default=640,
        help="Inference image size (square, in pixels). Default: 640.",
    )
    parser.add_argument(
        "--half", action="store_true",
        help="Export with FP16 precision. Recommended on Jetson Nano for the "
             "best speed/accuracy trade-off.",
    )
    parser.add_argument(
        "--int8", action="store_true",
        help="Export with INT8 precision (requires a calibration dataset "
             "configured via Ultralytics' export API). Mutually exclusive "
             "with --half.",
    )
    parser.add_argument(
        "--dynamic", action="store_true",
        help="Enable dynamic input shapes. Not recommended for HOLO-PATROL's "
             "fixed-resolution DeepStream pipeline (1280x720 / 640x480).",
    )
    parser.add_argument(
        "--workspace", type=float, default=4.0,
        help="TensorRT builder workspace size in GiB. Default: 4.0 "
             "(keep this modest on the Jetson Nano's limited memory).",
    )
    parser.add_argument(
        "--device", default="0",
        help="CUDA device index (e.g. '0') or 'cpu'. Default: '0'.",
    )
    parser.add_argument(
        "--batch", type=int, default=1,
        help="Batch size baked into the engine. Default: 1, matching "
             "nvstreammux's batch-size=1 in the onboard pipeline.",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("engines"),
        help="Directory to place the exported .engine file in. Default: ./engines",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.weights.exists():
        print(f"❌ Weights file not found: {args.weights}", file=sys.stderr)
        return 1

    if args.half and args.int8:
        print("❌ --half and --int8 are mutually exclusive.", file=sys.stderr)
        return 1

    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "❌ The 'ultralytics' package is required for export.\n"
            "   Install it with: pip install ultralytics",
            file=sys.stderr,
        )
        return 1

    args.output.mkdir(parents=True, exist_ok=True)

    print(f"📦 Loading weights: {args.weights}")
    model = YOLO(str(args.weights))

    print(
        f"🚀 Exporting to TensorRT | imgsz={args.imgsz} | half={args.half} | "
        f"int8={args.int8} | dynamic={args.dynamic} | "
        f"workspace={args.workspace} GiB | device={args.device} | batch={args.batch}"
    )

    exported_path = model.export(
        format="engine",
        imgsz=args.imgsz,
        half=args.half,
        int8=args.int8,
        dynamic=args.dynamic,
        workspace=args.workspace,
        device=args.device,
        batch=args.batch,
    )

    final_path = args.output / Path(exported_path).name
    Path(exported_path).replace(final_path)

    print(f"✅ TensorRT engine written to: {final_path}")
    print(
        "\nNext step: point 'model-engine-file' in "
        "config_infer_primary_yoloV8.txt at this file, then restart "
        "the DeepStream pipeline (yaw_tracker.py / visual_tracker_3d.py)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
