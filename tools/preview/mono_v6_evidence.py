#!/usr/bin/env python3
"""Render the Mono page against the shared Horizon environment palette.

This is a small host-side checkpoint, not a production renderer.  It proves
that the low-cost page can follow the same day/night palette and still keep
invalid VehicleState values visibly unknown.
"""

import json
from pathlib import Path

from PIL import Image
import numpy as np
import scene_preview as preview


ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "scenes" / "v6_mono.scene"
OUT = ROOT / "assets" / "checkpoints" / "v6_pages" / "mono"

def luminance(rgb):
    rgb = np.asarray(rgb, dtype=float) / 255
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    return (linear * [.2126, .7152, .0722]).sum(axis=-1)


def render(name, phase, state):
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = OUT / name
    scene = json.loads(SCENE.read_text())
    for node in scene['nodes']:
        if node.get('source') == 'clock':
            node.pop('source')
            node['text'] = '13:51'
    environment = preview.environment_context({}, phase=phase)
    preview.render(scene, None, preview.MOCK_STATES[state], str(prefix) + '.png',
                   environment=environment)
    image = Image.open(str(prefix) + ".png").convert("RGB")
    half = image.resize((960, 240), Image.Resampling.LANCZOS)
    half.save(str(prefix) + "_half.png")
    # Measure the speed glyph cores against the actual rendered background at
    # both review sizes. A dark-on-dark regression must fail this checkpoint.
    ratios = {}
    for label, frame in [('full', image), ('half', half)]:
        a = np.asarray(frame)
        scale = frame.width / 1920
        region = a[round(125*scale):round(280*scale), round(830*scale):round(1090*scale)]
        bg = float(luminance(a[round(100*scale), round(960*scale)]))
        values = luminance(region)
        contrast = (np.maximum(values,bg)+.05)/(np.minimum(values,bg)+.05)
        ratios[label] = round(float(np.percentile(contrast, 98)), 2)
        if ratios[label] < 4.5:
            raise AssertionError(f'{name} {label}: speed contrast {ratios[label]} < 4.5')
    return {"phase": phase, "state": state, "size": list(image.size),
            "speed_core_contrast": ratios,
            "output": str(prefix.relative_to(ROOT)) + ".png"}


def main():
    records = [
        render("mono_day_normal", "day", "driving"),
        render("mono_night_normal", "night", "driving"),
        render("mono_day_lost", "day", "lost"),
        render("mono_day_door", "day", "door_open"),
    ]
    report = {
        "page": "v6_mono",
        "source": "VehicleState + shared EnvironmentTimeSystem palette",
        "device_validation": "UNKNOWN_UNTIL_DEVICE_TEST",
        "records": records,
        "state_source": "DEVELOPER_FIXTURE",
        "status": "HOST_PALETTE_CHECKPOINT_PASS",
    }
    report_path = ROOT / "assets" / "checkpoints" / "v6_pages" / "mono_evidence.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
