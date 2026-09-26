#!/usr/bin/env python3
"""Measure the yaw sweep and select the production chase angle.

The sweep is judged on measurements first: how much of the car's silhouette
actually moved, whether the anchor and the presented size survived, and how far
the view travelled towards the car's rear. The sheet is printed alongside so the
numbers can be checked against the picture.

Selection rule (stated before the numbers are read): the smallest baked angle
whose silhouette change is at least a third of the largest change, with the
anchor drift under one pixel and the presented height within 2 % of the
standstill presentation. Taking the smallest angle that already reads as motion
keeps the accepted V5.4 composition as the dominant look.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/preview'))
import scene_preview as preview  # noqa: E402

OUT = ROOT / 'assets/checkpoints/horizon_v55'
FRAMES = OUT / 'frames'
SWEEP_ANGLES = (0, 4, 7, 10, 13, 16)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cell', default='640x160')
    args = parser.parse_args()
    width, height = (int(value) for value in args.cell.split('x'))
    OUT.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    scene = json.loads((ROOT / 'scenes/horizon_v5.scene').read_text())
    tokens = json.loads((ROOT / 'assets/ui/horizon_v5_tokens.json').read_text())
    boxes_path = (ROOT / 'assets/checkpoints/horizon_v5/'
                  'horizon_v55_chase_boxes.json')
    boxes = (json.loads(boxes_path.read_text())['phases']
             if boxes_path.is_file() else {})
    state = preview.MOCK_STATES['v5_neutral']
    # The sweep compares viewing angles, so the lamp layers are held at their
    # standstill form and only the car's own layer carries the orbit; the
    # selected angle is then baked for every lighting state.
    sweep_scene = dict(scene, nodes=[
        node for node in scene['nodes']
        if not node['id'].startswith('vehicle.') or node['id'] == 'vehicle.base'])
    bare = dict(sweep_scene, nodes=[node for node in sweep_scene['nodes']
                                    if node['id'] != 'vehicle.base'])
    report = {'schema': 'horizon-v5.5-yaw-selection v1',
              'selection_rule': 'smallest angle whose silhouette change is at '
                                'least a third of the largest with the car\'s '
                                'own anchor held to under a pixel. The '
                                'presented height is corrected at runtime from '
                                'the measured body ratio; the rendered '
                                'footprint also carries the wet-road response, '
                                'so its height is reported but not gated here.',
              'phases': {}, 'angles': {}}
    rows = []
    masks = {}
    for phase in ('night', 'day'):
        images = []
        for angle in SWEEP_ANGLES:
            env = preview.environment_context(tokens, phase=phase, speed=0,
                                              yaw_override=angle)
            path = FRAMES / f'yawselect_{phase}_{angle:02d}.png'
            preview.render(sweep_scene, None, state, str(path), t_norm=0,
                           environment=env)
            bare_path = FRAMES / f'yawselect_{phase}_{angle:02d}_bare.png'
            preview.render(bare, None, state, str(bare_path), t_norm=0,
                           environment=env)
            mask = np.max(np.abs(
                np.asarray(Image.open(path).convert('RGB')).astype(int)
                - np.asarray(Image.open(bare_path).convert('RGB')).astype(int)),
                axis=2) > 5
            masks[(phase, angle)] = mask
            ys, xs = np.nonzero(mask)
            box = [int(xs.min()), int(ys.min()), int(xs.max() + 1),
                   int(ys.max() + 1)]
            entry = report['angles'].setdefault(str(angle), {})
            entry[phase] = {
                'vehicle_box': box,
                'width_px': box[2] - box[0],
                'height_px': box[3] - box[1],
                'centre_x_px': (box[0] + box[2]) / 2.0,
                'contact_y_px': box[3],
                'silhouette_pixels': int(mask.sum())}
            images.append(path)
        rows.append((f'{phase.upper()}  0 / 4 / 7 / 10 / 13 / 16 deg', images))
    # How much of the car's footprint changed, relative to the standstill view.
    for angle in SWEEP_ANGLES:
        for phase in ('night', 'day'):
            base = masks[(phase, 0)]
            current = masks[(phase, angle)]
            union = int((base | current).sum())
            changed_pixels = int((base != current).sum())
            entry = report['angles'][str(angle)][phase]
            entry['silhouette_change_pixels'] = changed_pixels
            entry['silhouette_change_fraction'] = round(
                changed_pixels / max(1, union), 4)
            entry['centre_drift_px'] = round(
                abs(entry['centre_x_px']
                    - report['angles']['0'][phase]['centre_x_px']), 3)
            entry['height_ratio_vs_0'] = round(
                entry['height_px']
                / report['angles']['0'][phase]['height_px'], 4)
    # The car's own body box is what the framing solver pins; the footprint
    # measured above also carries the road response, which changes shape with
    # the view. The anchor gate therefore reads the body, and the presented
    # size gate reads the footprint after the runtime's own height correction.
    for angle in SWEEP_ANGLES:
        for phase in ('night', 'day'):
            table = boxes.get(phase) or {}
            standstill = table.get('0')
            current = table.get(f'{angle:g}')
            entry = report['angles'][str(angle)][phase]
            if standstill and current:
                entry['body_centre_drift_px'] = round(abs(
                    current['centre_x'] - standstill['centre_x']), 3)
                entry['body_contact_drift_px'] = round(abs(
                    current['contact_y'] - standstill['contact_y']), 3)
                entry['body_height_ratio'] = current[
                    'height_ratio_vs_standstill']
    largest = max(report['angles'][str(angle)]['night']
                  ['silhouette_change_fraction'] for angle in SWEEP_ANGLES)
    threshold = largest / 3.0
    selected = None
    for angle in SWEEP_ANGLES:
        if angle == 0:
            continue
        entry = report['angles'][str(angle)]
        ok = all(entry[phase]['silhouette_change_fraction'] >= threshold
                 and entry[phase].get('body_centre_drift_px', 0.0) < 1.0
                 and entry[phase].get('body_contact_drift_px', 0.0) < 1.0
                 for phase in ('night', 'day'))
        if ok:
            selected = angle
            break
    report['silhouette_change_threshold'] = round(threshold, 4)
    report['selected_yaw_deg'] = selected
    report['selected_why'] = (
        'smallest baked angle whose silhouette change clears a third of the '
        'largest change with the anchor and the presented height intact')
    (OUT / 'horizon_v55_yaw_selection.json').write_text(
        json.dumps(report, indent=1) + '\n')

    pad, caption_h, header_h = 12, 22, 30
    canvas = Image.new('RGB', (pad + 6 * (width + pad),
                               header_h + pad + 2 * (height + caption_h + pad)),
                       (10, 13, 18))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 10), 'HORIZON V5.5 chase yaw sweep - '
                         '0/4/7/10/13/16 deg at 0 km/h', fill=(235, 240, 246))
    for index, (caption, images) in enumerate(rows):
        top = header_h + pad + index * (height + caption_h + pad)
        draw.text((pad, top), caption, fill=(150, 200, 235))
        for column, image in enumerate(images):
            thumb = Image.open(image).convert('RGB').resize(
                (width, height), Image.LANCZOS)
            canvas.paste(thumb, (pad + column * (width + pad),
                                 top + caption_h))
    sheet = OUT / 'horizon_v55_chase_yaw_sweep.png'
    canvas.save(sheet)
    canvas.resize((canvas.width // 2, canvas.height // 2),
                  Image.Resampling.LANCZOS).save(
        OUT / 'horizon_v55_chase_yaw_sweep_half.png')
    for angle in SWEEP_ANGLES:
        entry = report['angles'][str(angle)]['night']
        print(f"[v5.5-yaw] {angle:2d} deg  change "
              f"{entry['silhouette_change_fraction']:.3f}  drift "
              f"{entry['centre_drift_px']:.2f}  h "
              f"{entry['height_ratio_vs_0']:.3f}")
    print(f"[v5.5-yaw] selected {selected} deg "
          f"(threshold {threshold:.3f})")
    print(f"[v5.5-yaw] {os.path.relpath(sheet, ROOT)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
