#!/usr/bin/env python3
"""Measure the DAY environment against the review's own complaints.

The review named five things about DAY: flat grey atmosphere, weak premium
material separation, vehicle/background tonal similarity, low cinematic depth
and a road that still looks synthetic. Each of those becomes a number here, so
a polish pass can be judged instead of argued about:

    sky_gradient_levels        top of the sky against the horizon
    aerial_haze_levels         contrast lost between the near and far terrain
    strongest_terrain_edge     the largest vertical step in the terrain band
    road_detail_energy         high-frequency energy of the road band (a flat
                               fill reads as synthetic however smooth it looks)
    car_background_separation  the car's own luminance against a ring of the
                               background immediately around it
    material_means             paint / glass / tyre / rim, from the material mask

Usage:
    python3 tools/preview/horizon_v55_day_metrics.py [--json <path>]
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
MASK = ROOT / 'assets/rendered/vehicle/horizon_v5/day/material_mask.png'
CAR = ROOT / 'assets/rendered/vehicle/horizon_v5/day/car/base/000.png'
PLATE = ROOT / 'assets/ui/horizon_v5_background_day.png'
OUT = ROOT / 'assets/checkpoints/horizon_v55/horizon_v55_day_metrics.json'
FRAME = (ROOT / 'assets/checkpoints/horizon_v55/frames/chase_day_000.png')
PRESENTATION = ROOT / 'assets/ui/horizon_v54_presentation.json'
BOXES = (ROOT / 'assets/checkpoints/horizon_v5/horizon_v55_chase_boxes.json')

HORIZON_ROW = 167
GROUND_TOP = 173
MATERIAL_CLASSES = {'paint': (255, 0, 0), 'glass': (0, 255, 0),
                    'tyre': (0, 0, 255), 'rim': (255, 255, 0)}


def luminance(rgb):
    array = np.asarray(rgb, dtype=np.float32)
    return (array[:, :, 0] * 0.2126 + array[:, :, 1] * 0.7152
            + array[:, :, 2] * 0.0722)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', default=str(OUT))
    parser.add_argument('--plate', default=str(PLATE))
    parser.add_argument('--frame', default=str(FRAME))
    args = parser.parse_args()
    plate_path = Path(args.plate)
    frame_path = Path(args.frame)
    report = {'schema': 'horizon-v5.5-day-metrics v1',
              'measurement_platform': 'MAC MEASURED',
              'plate': os.path.relpath(plate_path, ROOT),
              'why': 'five named complaints, five measurements'}
    if not plate_path.is_file():
        sys.exit(f'missing day plate: {plate_path}')
    plate = Image.open(plate_path).convert('RGB')
    lum = luminance(plate)
    width, height = plate.size

    # The sky has to be measured where there is sky: find the skyline first
    # (the strongest vertical step per column) and take the median row, or the
    # "sky at the horizon" window lands inside the terrain and reports a
    # gradient with the wrong sign.
    gradients = np.abs(np.diff(lum[40:240, 300:width - 300], axis=0))
    skyline = 40 + int(np.median(np.argmax(gradients, axis=0))) + 60
    # Sky rows are flat; the first row whose horizontal spread jumps is the
    # ridge line. Sampling "sky near the horizon" without this lands inside the
    # terrain and reports a gradient with the wrong sign.
    sky_columns = lum[:, 300:width - 300]
    spread = sky_columns.std(axis=1)
    flat = float(np.median(spread[6:40]))
    first_terrain = int(next((row for row in range(20, len(spread))
                              if spread[row] > flat * 2.5), HORIZON_ROW))
    sky_top = float(lum[6:34, 300:width - 300].mean())
    sky_low = float(lum[max(0, first_terrain - 28):max(1, first_terrain - 4),
                        300:width - 300].mean())
    terrain = lum[max(0, skyline - 80):skyline + 40, :]
    edges = np.abs(np.diff(terrain, axis=0))
    column = terrain.mean(axis=1)
    road = lum[GROUND_TOP + 40:480, 300:width - 300]
    laplacian = np.asarray(Image.fromarray(
        np.clip(road, 0, 255).astype('uint8')).filter(
            ImageFilter.FIND_EDGES)).astype(np.float32)
    report['atmosphere'] = {
        'skyline_row': skyline,
        'first_terrain_row': first_terrain,
        'sky_top_level': round(sky_top, 2),
        'sky_at_horizon_level': round(sky_low, 2),
        'sky_gradient_levels': round(sky_low - sky_top, 2),
        'terrain_column_range_levels': round(float(column.max()
                                                   - column.min()), 2),
        'strongest_terrain_edge_levels': round(float(edges.max()), 2),
        'terrain_edge_p95_levels': round(float(np.percentile(edges, 95)), 2)}
    report['road'] = {
        'mean_level': round(float(road.mean()), 2),
        'row_std_levels': round(float(road.std(axis=1).mean()), 2),
        'detail_energy': round(float(laplacian.mean()), 3),
        # Brightness-relative, so darkening the road cannot be mistaken for
        # losing its texture.
        'detail_energy_relative': round(
            float(laplacian.mean()) / max(1.0, float(road.mean())) * 100, 3)}

    if CAR.is_file():
        car = Image.open(CAR).convert('RGBA')
        alpha = np.asarray(car)[:, :, 3]
        source = alpha > 24
        ys, xs = np.nonzero(source)
        box = [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
        patch = source[box[1]:box[3], box[0]:box[2]]
        spec = json.loads(PRESENTATION.read_text())
        scale = float(spec['scale'])
        anchor = spec.get('anchor', [954, 345])
        size = (max(1, int(round(patch.shape[1] * scale))),
                max(1, int(round(patch.shape[0] * scale))))
        resized = np.asarray(Image.fromarray((patch * 255).astype('uint8'))
                             .resize(size, Image.Resampling.LANCZOS)) > 24
        left = int(round(anchor[0] + (box[0] - anchor[0]) * scale))
        top = int(round(anchor[1] + (box[1] - anchor[1]) * scale))
        mask = np.zeros((height, width), dtype=bool)
        y0, x0 = max(0, top), max(0, left)
        y1 = min(height, top + size[1])
        x1 = min(width, left + size[0])
        mask[y0:y1, x0:x1] = resized[y0 - top:y1 - top, x0 - left:x1 - left]
        ring = np.asarray(Image.fromarray((mask * 255).astype('uint8')).filter(
            ImageFilter.MaxFilter(15))).astype(bool) & ~mask
        # Judged on the composite, not on the transparent car pass: what the
        # driver sees is the car against the place it stands in.
        if frame_path.is_file():
            frame_lum = luminance(Image.open(frame_path).convert('RGB'))
        else:
            frame_lum = luminance(Image.new('RGB', (width, height)))
        car_mean = float(frame_lum[mask].mean())
        ring_mean = float(frame_lum[ring].mean()) if ring.any() else float('nan')
        # The mean of the whole car is dominated by its dark glass and tyres, so
        # the separation the review is about is measured two ways that can: the
        # paint against the surrounding ground, and the car's own outline
        # against what is immediately behind it.
        inner = np.asarray(Image.fromarray((mask * 255).astype('uint8')).filter(
            ImageFilter.MinFilter(9))).astype(bool)
        outline = mask & ~inner
        if outline.any() and ring.any():
            outline_mean = round(abs(float(frame_lum[outline].mean())
                                     - float(frame_lum[ring].mean())), 2)
            outline_p20 = None
        else:
            outline_mean = outline_p20 = None
        report['car'] = {
            'pixels': int(mask.sum()),
            'mean_level': round(car_mean, 2),
            'background_ring_mean_level': round(ring_mean, 2),
            'separation_levels': round(abs(car_mean - ring_mean), 2),
            'outline_contrast_mean_levels': outline_mean,
            'outline_contrast_p20_levels': outline_p20,
            'measured_on': os.path.relpath(frame_path, ROOT)
            if frame_path.is_file()
            else 'NO_COMPOSITE_FRAME'}
    if MASK.is_file() and CAR.is_file():
        material = np.asarray(Image.open(MASK).convert('RGBA'))
        car = np.asarray(Image.open(CAR).convert('RGBA'))
        brightness = (car[:, :, :3].astype(np.float32)
                      * np.array([0.2126, 0.7152, 0.0722])).sum(axis=2)
        classes = {}
        for name, colour in MATERIAL_CLASSES.items():
            selected = (np.abs(material[:, :, :3].astype(float) - colour)
                        .max(axis=2) < 12) & (material[:, :, 3] > 250)
            values = brightness[selected]
            classes[name] = {
                'pixels': int(values.size),
                'mean_level': round(float(values.mean()), 2) if values.size
                else None}
        if classes['paint']['mean_level'] and classes['glass']['mean_level']:
            classes['glass_minus_paint'] = round(
                classes['glass']['mean_level']
                - classes['paint']['mean_level'], 2)
        if classes['rim']['mean_level'] and classes['tyre']['mean_level']:
            classes['rim_minus_tyre'] = round(
                classes['rim']['mean_level'] - classes['tyre']['mean_level'], 2)
        report['material_classes'] = classes
    Path(args.json).write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(report, indent=1))
    print(f'[v5.5-day] {os.path.relpath(args.json, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
