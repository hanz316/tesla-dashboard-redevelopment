#!/usr/bin/env python3
"""Horizon V5.5 chase-camera and vehicle-motion evidence.

Every number here is measured from a render, not asserted: the yaw sweep is a
set of real camera orbits, the speed sheet is one render per speed through the
same motion vector the runtime reads, and the parallax is recovered by
cross-correlating the ground band between two frames.

Outputs (all 1:1 and half size):
    horizon_v55_chase_yaw_sweep.png      0/4/7/10/13/16 deg at standstill
    horizon_v55_speed_motion.png         0/10/30/60/80/120 km/h
    horizon_v55_vehicle_scale_trials.png current/+4/+7/+10 %
    horizon_v55_awareness_chase.png      10 states at 0 and 80 km/h
    horizon_v55_brake_motion.png         0/30/80/120 km/h braking
    horizon_v55_day_night_motion.png     DAY 0/80, NIGHT 0/80
    horizon_v55_chase_metrics.json       every measurement and gate
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/preview'))
sys.path.insert(0, str(ROOT / 'tools/assets'))
import scene_preview as preview  # noqa: E402
import horizon_v5_motion as motion  # noqa: E402

SCENE = ROOT / 'scenes/horizon_v5.scene'
TOKENS = ROOT / 'assets/ui/horizon_v5_tokens.json'
LAYOUT = ROOT / 'assets/ui/horizon_v5_layout.json'
OUT = ROOT / 'assets/checkpoints/horizon_v55'
# Intermediate frames are working evidence, not review artifacts: they stay
# local (gitignored) and only the sheets and the measurements are committed.
FRAMES = OUT / 'frames'
HORIZON_ROW = 167
GROUND_TOP = 173
SPEEDS = (0, 10, 30, 60, 80, 120)
SWEEP_ANGLES = (0, 4, 7, 10, 13, 16)
# The presentation the review started from, and the trial factors it asked for.
# The trials are a fixed experiment: they do not move when the selected scale
# changes, or the measurement would stop being reproducible.
SCALE_TRIAL_BASE = 1.09
SCALE_TRIAL_FACTORS = (("current", 1.00), ("+4%", 1.04), ("+7%", 1.07),
                       ("+10%", 1.10))

# The awareness states the chase camera has to keep semantically stable.
AWARENESS_STATES = (
    ("none", {}),
    ("left_turn", {'indicator_left': True, 'blind_left': False}),
    ("left_blind", {'blind_left': True}),
    ("left_conflict", {'blind_left': True, 'indicator_left': True}),
    ("right_turn", {'indicator_right': True, 'blind_right': False}),
    ("right_blind", {'blind_right': True}),
    ("right_conflict", {'blind_right': True, 'indicator_right': True}),
    ("both_blind", {'blind_left': True, 'blind_right': True}),
    ("hazard", {'hazards': True, 'blind_left': False, 'blind_right': False}),
    ("hazard_both", {'hazards': True, 'blind_left': True,
                     'blind_right': True}),
)


def load_documents():
    scene = json.loads(SCENE.read_text())
    # A fixed clock: two frames rendered a minute apart would otherwise differ
    # in the clock digits, and the standstill residual gate would read that as
    # motion.
    for node in scene['nodes']:
        if node['id'] == 'top.clock':
            node.pop('source', None)
            node['text'] = '13:51'
    tokens = json.loads(TOKENS.read_text())
    layout = json.loads(LAYOUT.read_text())
    return scene, tokens, layout


def base_state(scene):
    state = copy.deepcopy(preview.MOCK_STATES['v5_neutral'])
    state.setdefault('hazards', False)
    for key in ('blind_left', 'blind_right'):
        state.setdefault(key, False)
    return state


def environment(tokens, phase, speed, yaw_override=None):
    return preview.environment_context(tokens, phase=phase, speed=speed,
                                       yaw_override=yaw_override)


def render(scene, env, state, name, scale=None):
    target = scene
    if scale:
        target = copy.deepcopy(scene)
        for node in target['nodes']:
            if node['id'].startswith('vehicle.'):
                node['presentation'] = dict(node.get('presentation') or {},
                                            scale=scale)
    FRAMES.mkdir(parents=True, exist_ok=True)
    path = FRAMES / (name + '.png')
    preview.render(target, None, state, str(path), t_norm=0, environment=env)
    half = FRAMES / (name + '_half.png')
    Image.open(path).resize((960, 240), Image.Resampling.LANCZOS).save(half)
    return path


def pixels(path):
    return np.asarray(Image.open(path).convert('RGB')).astype(np.int16)


def changed(first, second, threshold=5):
    return np.max(np.abs(pixels(first) - pixels(second)), axis=2) > threshold


def bbox(mask):
    ys, xs = np.nonzero(mask)
    if not xs.size:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]


def without_nodes(scene, predicate):
    return dict(scene, nodes=[node for node in scene['nodes']
                              if not predicate(node['id'])])


def vehicle_footprint(scene, env, state, name, scale=None):
    """The pixels the vehicle layers are responsible for, and their box."""
    with_car = render(scene, env, state, name + '_with', scale=scale)
    without = render(without_nodes(scene, lambda i: i.startswith('vehicle.')),
                     env, state, name + '_without')
    mask = changed(with_car, without)
    return mask, bbox(mask)


def node_box(layout, node_id):
    for component in layout['components']:
        if component['id'] == node_id:
            bounds = component['bounds']
            return [bounds['x'], bounds['y'], bounds['x'] + bounds['w'],
                    bounds['y'] + bounds['h']]
    return None


def union_box(layout, prefix):
    boxes = [node_box(layout, component['id'])
             for component in layout['components']
             if component['id'].startswith(prefix)]
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


def vertical_shift(first, second, x0, x1, y0, y1, limit=14):
    """Measured vertical displacement of a strip, by correlation.

    Positive means the content moved towards the viewer (down the panel), which
    is the direction the screen motion vector declares for road-level detail.
    """
    a = pixels(first)[y0:y1, x0:x1].mean(axis=2)
    b = pixels(second)[y0:y1, x0:x1].mean(axis=2)
    best, best_score = 0, None
    for shift in range(-limit, limit + 1):
        moved = np.roll(b, shift, axis=0)
        overlap = slice(max(0, shift), a.shape[0] - max(0, -shift))
        if overlap.stop - overlap.start < 8:
            continue
        score = float(np.abs(a[overlap] - moved[overlap]).mean())
        if best_score is None or score < best_score:
            best, best_score = shift, score
    # `roll(b, +k)` moves b's content down; if that is what aligns the two
    # frames, the content moved down by k, so the displacement is +k.
    return -best


def sheet(rows, path, title, columns=None, cell=(640, 160)):
    """A captioned contact sheet; rows is a list of (caption, [images])."""
    pad, caption_h, header_h = 12, 22, 34
    widths = [len(images) for _caption, images in rows]
    columns = columns or max(widths)
    width = pad + columns * (cell[0] + pad)
    height = header_h + pad + len(rows) * (cell[1] + caption_h + pad)
    canvas = Image.new('RGB', (width, height), (10, 13, 18))
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 10), title, fill=(235, 240, 246))
    for index, (caption, images) in enumerate(rows):
        top = header_h + pad + index * (cell[1] + caption_h + pad)
        draw.text((pad, top), caption, fill=(150, 200, 235))
        for column, image in enumerate(images):
            thumb = Image.open(image).convert('RGB').resize(cell,
                                                            Image.LANCZOS)
            left = pad + column * (cell[0] + pad)
            canvas.paste(thumb, (left, top + caption_h))
    canvas.save(path)
    half = path.with_name(path.stem + '_half.png')
    canvas.resize((max(1, width // 2), max(1, height // 2)),
                  Image.Resampling.LANCZOS).save(half)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default=str(OUT))
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    scene, tokens, layout = load_documents()
    state = base_state(scene)
    boxes_report = json.loads((ROOT / 'assets/checkpoints/horizon_v5/'
                               'horizon_v55_chase_boxes.json').read_text())
    presentation = json.loads((ROOT / 'assets/ui/horizon_v54_presentation.json')
                              .read_text())
    current_scale = float(presentation['scale'])
    anchor = presentation.get('anchor', [954, 345])

    def presented_body_box(phase, scale, yaw=0.0):
        """The car's own box on the panel: measured per phase, then scaled.

        The rendered footprint also carries the wet-road response, which in
        daylight is a completely different shape from the night one, so the
        DAY/NIGHT size contract has to be judged on the car itself.
        """
        entry = (boxes_report['phases'].get(phase) or {}).get(f'{yaw:g}')
        if not entry:
            return None
        box = entry['box']
        return [round(anchor[index % 2]
                      + (value - anchor[index % 2]) * scale)
                for index, value in enumerate(box)]

    report = {'schema': 'horizon-v5.5-chase-evidence v1',
              'measurement_platform': 'MAC MEASURED',
              'device': 'UNKNOWN_UNTIL_DEVICE_TEST',
              'state_source': 'DEVELOPER_FIXTURE',
              'motion': {}, 'yaw_sweep': {}, 'scale_trials': {},
              'awareness': {}, 'brake': {}, 'day_night': {}}

    # ---------------------------------------------------------- yaw sweep
    sweep_rows = []
    neutral_env = environment(tokens, 'night', 0)
    reference = None
    for angle in SWEEP_ANGLES:
        env = environment(tokens, 'night', 0, yaw_override=angle)
        path = render(scene, env, state, f'chase_yaw_{angle:02d}')
        mask, box = vehicle_footprint(scene, env, state,
                                      f'chase_yaw_{angle:02d}_car')
        if reference is None:
            reference = box
        pixels_count = int(mask.sum())
        report['yaw_sweep'][f'{angle}'] = {
            'yaw_deg': env['chase_yaw_deg'],
            'vehicle_box': box,
            'vehicle_pixels': pixels_count,
            'body_box': presented_body_box('night', current_scale, angle),
            'box_width_px': box[2] - box[0],
            'box_height_px': box[3] - box[1],
            'anchor_centre_x_px': (box[0] + box[2]) / 2.0,
            'anchor_contact_y_px': box[3],
            'box_centre_drift_px': abs((box[0] + box[2]) / 2.0
                                       - (reference[0] + reference[2]) / 2.0),
            'box_height_ratio_vs_0': round((box[3] - box[1])
                                           / (reference[3] - reference[1]), 4)}
        sweep_rows.append((f'yaw +{angle} deg   box {box[2]-box[0]}x'
                           f'{box[3]-box[1]}  drift '
                           f'{report["yaw_sweep"][str(angle)]["box_centre_drift_px"]:.0f} px',
                           [path]))
    sheet(sweep_rows, OUT / 'horizon_v55_chase_yaw_sweep.png',
          'HORIZON V5.5 chase yaw sweep - 0/4/7/10/13/16 deg at 0 km/h')

    # ------------------------------------------------------- speed motion
    motion_rows = []
    zero = render(scene, environment(tokens, 'night', 0), state,
                  'chase_speed_000')
    wheel_band = union_box(layout, 'motion.wheel')
    wake_box = node_box(layout, 'motion.wake')
    road_band = [284, GROUND_TOP, 1636, 480]
    for speed in SPEEDS:
        env = environment(tokens, 'night', speed)
        path = render(scene, env, state, f'chase_speed_{speed:03d}')
        mask = changed(zero, path)
        wheel_mask = np.zeros_like(mask)
        wheel_mask[wheel_band[1]:wheel_band[3], wheel_band[0]:wheel_band[2]] = True
        wake_mask = np.zeros_like(mask)
        wake_mask[wake_box[1]:wake_box[3], wake_box[0]:wake_box[2]] = True
        road_mask = np.zeros_like(mask)
        road_mask[road_band[1]:road_band[3], road_band[0]:road_band[2]] = True
        measured = vertical_shift(zero, path, 900, 1010, GROUND_TOP, 470)
        # The band's own translation, measured with the motion overlays removed:
        # the road-flow streaks move much further than the band and would
        # otherwise dominate the correlation.
        band_only = render(without_nodes(scene, lambda i: i.startswith('motion.')),
                           env, state, f'chase_speed_band_{speed:03d}')
        band_zero = render(without_nodes(scene, lambda i: i.startswith('motion.')),
                           environment(tokens, 'night', 0), state,
                           'chase_speed_band_000')
        band_shift = vertical_shift(band_zero, band_only, 900, 1010, GROUND_TOP, 470)
        vector = motion.screen_motion_vector(speed)
        report['motion'][f'{speed}'] = {
            'chase_yaw_deg': vector['chase_yaw_deg'],
            'changed_pixels': int(mask.sum()),
            'changed_in_wheel_band': int((mask & wheel_mask).sum()),
            'changed_in_wake_box': int((mask & wake_mask).sum()),
            'changed_in_road_band': int((mask & road_mask).sum()),
            'measured_ground_shift_px': int(measured),
            'measured_band_shift_px': int(band_shift),
            'declared_parallax_near_px': vector[
                'environment_parallax_px']['near'],
            'declared_road_flow_px': vector['road_flow_offset_px'],
            'reflection_stretch': vector['reflection_stretch']}
        motion_rows.append((f'{speed} km/h   yaw {vector["chase_yaw_deg"]:.1f}'
                            f'   ground {measured} px   road '
                            f'{vector["road_flow_offset_px"]:.0f} px',
                            [path]))
    sheet(motion_rows, OUT / 'horizon_v55_speed_motion.png',
          'HORIZON V5.5 speed motion - 0/10/30/60/80/120 km/h')

    # ------------------------------------------------------- scale trials
    current = current_scale
    scale_rows = []
    report['selected_presentation_scale'] = current
    for label, factor in SCALE_TRIAL_FACTORS:
        scale = round(SCALE_TRIAL_BASE * factor, 4)
        entry = {'scale': scale, 'selected': abs(scale - current) < 1e-6,
                 'phases': {}}
        for phase in ('day', 'night'):
            env = environment(tokens, phase, 0)
            name = f'chase_scale_{label.replace("+", "p").replace("%", "")}_{phase}'
            path = render(scene, env, state, name, scale=scale)
            _mask, box = vehicle_footprint(scene, env, state, name + '_car',
                                           scale=scale)
            zones = layout['zones']
            body = presented_body_box(phase, scale)
            nav = node_box(layout, 'nav.capsule')
            mask_cut_at_contact = 116 + (51 - 116) * body[3] / 480.0
            entry['phases'][phase] = {
                'body_box': body,
                'body_width_px': body[2] - body[0],
                'body_height_px': body[3] - body[1],
                'footprint_box': box,
                'speed_zone_clearance_px': body[0] - zones['driver']['right'],
                'energy_zone_clearance_px': zones['energy']['right'] - body[2],
                'navigation_clearance_px': body[1] - nav[3],
                'trapezoid_mask_clearance_px': round(
                    body[0] - mask_cut_at_contact, 1),
                'bottom_clearance_px': 480 - body[3]}
            if phase == 'night':
                scale_rows.append((f'{label}   body '
                                   f'{body[2]-body[0]}x{body[3]-body[1]}'
                                   f'   speed '
                                   f'{entry["phases"][phase]["speed_zone_clearance_px"]:.0f}'
                                   f'   energy '
                                   f'{entry["phases"][phase]["energy_zone_clearance_px"]:.0f}',
                                   [path]))
        day = entry['phases']['day']
        night = entry['phases']['night']
        entry['phase_body_box_max_delta_px'] = max(
            abs(day['body_box'][i] - night['body_box'][i])
            for i in range(4))
        entry['phase_width_delta_px'] = abs(day['body_width_px']
                                            - night['body_width_px'])
        entry['phase_height_delta_px'] = abs(day['body_height_px']
                                             - night['body_height_px'])
        entry['phase_footprint_max_delta_px'] = max(
            abs(day['footprint_box'][i] - night['footprint_box'][i])
            for i in range(4))
        report['scale_trials'][label] = entry
    sheet(scale_rows, OUT / 'horizon_v55_vehicle_scale_trials.png',
          'HORIZON V5.5 vehicle scale trials - current/+4/+7/+10 %')

    # --------------------------------------------------- awareness chase
    awareness_rows = []
    awareness_nodes = [node for node in scene['nodes']
                       if node['id'].startswith('awareness.')]
    zone_nodes = [node for node in awareness_nodes
                  if not node['id'].endswith('.ghost')]
    ghost_nodes = [node for node in awareness_nodes
                   if node['id'].endswith('.ghost')]

    def body_mask_on_panel(phase, scale):
        """The car's own pixels on the panel, from its measured alpha."""
        entry = (boxes_report['phases'].get(phase) or {}).get('0')
        if not entry:
            return None
        alpha = np.asarray(Image.open(ROOT / entry['source']).convert('RGBA'))
        box = entry['box']
        patch = alpha[box[1]:box[3], box[0]:box[2], 3]
        width = max(1, int(round(patch.shape[1] * scale)))
        height = max(1, int(round(patch.shape[0] * scale)))
        resized = np.asarray(Image.fromarray(patch).resize(
            (width, height), Image.Resampling.LANCZOS))
        left = int(round(anchor[0] + (box[0] - anchor[0]) * scale))
        top = int(round(anchor[1] + (box[1] - anchor[1]) * scale))
        mask = np.zeros((480, 1920), dtype=bool)
        y0, x0 = max(0, top), max(0, left)
        y1, x1 = min(480, top + height), min(1920, left + width)
        if y1 > y0 and x1 > x0:
            mask[y0:y1, x0:x1] = resized[y0 - top:y1 - top,
                                        x0 - left:x1 - left] > 8
        return mask
    for speed in (0, 80):
        env = environment(tokens, 'day', speed)
        layer = dict(scene, nodes=awareness_nodes)
        left = render(layer, {}, {'blind_left': True},
                      f'chase_awareness_layer_left_{speed:03d}')
        right = render(layer, {}, {'blind_right': True},
                       f'chase_awareness_layer_right_{speed:03d}')
        empty = render(layer, {}, {}, f'chase_awareness_layer_empty_{speed:03d}')
        left_delta = pixels(left) - pixels(empty)
        right_delta = (pixels(right) - pixels(empty))[:, ::-1]
        report['awareness'][f'mirror_{speed}'] = {
            'max_channel_error': int(np.abs(left_delta - right_delta).max())}
        ghost = dict(scene, nodes=[node for node in awareness_nodes
                                   if node['id'].endswith('.ghost')])
        ghost_path = render(ghost, {}, {'blind_left': True},
                            f'chase_awareness_ghost_{speed:03d}')
        ghost_empty = render(ghost, {}, {},
                             f'chase_awareness_ghost_empty_{speed:03d}')
        ghost_mask = changed(ghost_path, ghost_empty)
        body_mask = body_mask_on_panel('day', current)
        # Pixels, not rectangles: the car's own alpha against the ghost's, so a
        # wet-road response that happens to reach the ghost is not counted as
        # the ghost sitting on the car.
        overlap = int((ghost_mask & body_mask).sum()) if body_mask is not None \
            else -1
        report['awareness'][f'ghost_body_overlap_{speed}'] = {
            'overlap_pixels': overlap, 'ghost_box': bbox(ghost_mask),
            'body_box': bbox(body_mask) if body_mask is not None else None}
    for speed in (0, 80):
        env = environment(tokens, 'day', speed)
        row = []
        for name, extra in AWARENESS_STATES:
            fixture = dict(state, **extra)
            path = render(scene, env, fixture,
                          f'chase_awareness_{name}_{speed:03d}')
            row.append(path)
            # Measured on the awareness layer alone: the panel around it is not
            # what this gate is about, and the vehicle's own lamp layers would
            # otherwise land inside the information band and be counted here.
            # The band gate is about the peripheral field, which is a safety
            # light: the ghost is a proximity cue drawn beside the car and is
            # measured against the car's own body instead.
            layer = dict(scene, nodes=zone_nodes)
            neutral_path = render(layer, {}, state,
                                  f'chase_awareness_zone_neutral_{speed:03d}')
            state_path = render(layer, {}, fixture,
                                f'chase_awareness_zone_{name}_{speed:03d}')
            mask = changed(neutral_path, state_path)
            zones = layout['zones']
            band_left = min(zone['x'] for zone in zones.values())
            band_right = max(zone['right'] for zone in zones.values())
            report['awareness'][f'{name}_{speed}'] = {
                'changed_pixels': int(mask.sum()),
                'box': bbox(mask),
                'information_band_overlap_pixels': int(
                    mask[:, band_left:band_right].sum())}
        awareness_rows.append((f'{speed} km/h   ' + ', '.join(
            f'{name} {report["awareness"][f"{name}_{speed}"]["changed_pixels"]}'
            for name, _extra in AWARENESS_STATES), row))
    sheet(awareness_rows, OUT / 'horizon_v55_awareness_chase.png',
          'HORIZON V5.5 awareness under chase camera - 0 and 80 km/h',
          cell=(384, 96))

    # ------------------------------------------------------------- brake
    brake_rows = []
    for speed in (0, 30, 80, 120):
        env = environment(tokens, 'night', speed)
        path = render(scene, env, dict(state, brake=True),
                      f'chase_brake_{speed:03d}')
        normal = render(scene, env, state, f'chase_brake_ref_{speed:03d}')
        mask = changed(normal, path)
        report['brake'][f'{speed}'] = {
            'changed_pixels': int(mask.sum()),
            'box': bbox(mask),
            'below_contact_changed_pixels': int(mask[345:, :].sum())}
        brake_rows.append((f'{speed} km/h   brake changed '
                           f'{report["brake"][str(speed)]["changed_pixels"]}'
                           f'   below contact '
                           f'{report["brake"][str(speed)]["below_contact_changed_pixels"]}',
                           [path]))
    sheet(brake_rows, OUT / 'horizon_v55_brake_motion.png',
          'HORIZON V5.5 braking - 0/30/80/120 km/h')

    # -------------------------------------------------------- day/night
    daynight_rows = []
    daynight_row = []
    for phase in ('day', 'night'):
        for speed in (0, 80):
            env = environment(tokens, phase, speed)
            path = render(scene, env, state,
                          f'chase_{phase}_{speed:03d}')
            daynight_row.append(path)
            _mask, box = vehicle_footprint(scene, env, state,
                                           f'chase_{phase}_{speed:03d}_car')
            body = presented_body_box(phase, current_scale)
            report['day_night'][f'{phase}_{speed}'] = {
                'vehicle_box': box, 'footprint_width_px': box[2] - box[0],
                'footprint_height_px': box[3] - box[1],
                'body_box': body,
                'body_width_px': body[2] - body[0],
                'body_height_px': body[3] - body[1],
                'yaw_deg': env['chase_yaw_deg']}
    daynight_rows.append(('DAY 0 / DAY 80 / NIGHT 0 / NIGHT 80',
                          daynight_row))
    sheet(daynight_rows, OUT / 'horizon_v55_day_night_motion.png',
          'HORIZON V5.5 day/night motion', cell=(640, 160))

    # ------------------------------------------------------------- gates
    def decoded(path):
        with Image.open(path) as bitmap:
            return bitmap.width * bitmap.height * 4

    def layer_inventory(phase, yaw):
        total = 0
        count = 0
        for manifest in (preview.vehicle_manifest_path(ROOT, phase, yaw),):
            if not os.path.isfile(manifest):
                continue
            entries = json.loads(Path(manifest).read_text())['layers']
            for entry in entries.values():
                path = ROOT / entry['source']
                if os.path.isfile(path):
                    total += decoded(path)
                    count += 1
        return total, count
    yaws = preview.chase_yaw_variants(str(ROOT)) if hasattr(
        preview, 'chase_yaw_variants') else []
    variant_bytes = {}
    for angle in [0.0] + list(yaws):
        for phase in ('night', 'day'):
            total, count = layer_inventory(phase, angle)
            variant_bytes[f'yaw{angle:g}_{phase}'] = {
                'decoded_rgba_bytes': total, 'layers': count}
    resident, resident_layers = layer_inventory('night', 0.0)
    plates = json.loads((ROOT / 'assets/ui/horizon_v5_environment.json')
                        .read_text())['plates']
    plate_bytes = {name: decoded(ROOT / path) for name, path in plates.items()}
    ground_report = json.loads((ROOT / 'assets/checkpoints/horizon_v5/'
                                'horizon_v55_ground_band.json').read_text())
    ground_bytes = {name: entry['decoded_rgba_bytes']
                    for name, entry in ground_report['phases'].items()}
    awareness_files = sorted((ROOT / 'assets/ui').glob('horizon_v54_*.png'))
    awareness_bytes = sum(decoded(path) for path in awareness_files)
    overlay_bytes = sum(decoded(ROOT / component['src'])
                        for component in layout['components']
                        if component.get('src')
                        and 'assets/ui/horizon_v5_' in component['src']
                        and os.path.isfile(ROOT / component['src']))
    report['performance'] = {
        'measurement_platform': 'MAC MEASURED',
        'device_estimate': 'T113 ESTIMATED',
        'device': 'UNKNOWN_UNTIL_DEVICE_TEST',
        'png_file_bytes_on_disk_is_not_ram': True,
        'yaw_variant_sets': variant_bytes,
        'resident_if_night_standstill': {
            'vehicle_layers_decoded_bytes': resident,
            'vehicle_layers': resident_layers,
            'environment_plates_decoded_bytes': plate_bytes,
            'ground_band_decoded_bytes': ground_bytes,
            'awareness_assets_decoded_bytes': awareness_bytes,
            'ui_overlays_decoded_bytes': overlay_bytes},
        'composited_layers_per_frame': 'environment plate + ground band + one '
                                       'vehicle stack + motion overlays + '
                                       'awareness + UI; no runtime blur, no '
                                       '3D, no resampling of the plate'}
    ui_ids = ('speed.', 'energy.', 'driver.', 'gear.', 'climate.', 'top.',
              'nav.', 'speedlimit.')
    ui_nodes = [node for node in scene['nodes']
                if node['id'].startswith(ui_ids)]
    ui_zero = render(dict(scene, nodes=ui_nodes),
                     environment(tokens, 'day', 0), state, 'chase_ui_000')
    ui_fast = render(dict(scene, nodes=ui_nodes),
                     environment(tokens, 'day', 120), state, 'chase_ui_120')
    yaws = [motion.screen_motion_vector(speed)['chase_yaw_deg']
            for speed in sorted(SPEEDS)]
    gates = {
        'yaw_zero_at_standstill': abs(yaws[0]) < 1e-9,
        'yaw_monotonic_with_speed': all(a <= b + 1e-9
                                        for a, b in zip(yaws, yaws[1:])),
        'yaw_continuous': max(abs(b - a) for a, b in zip(yaws, yaws[1:])) < 4.0,
        'standstill_motion_residual_pixels': int(
            changed(zero, render(scene, environment(tokens, 'night', 0), state,
                                 'chase_speed_zero_repeat')).sum()),
        'yaw_sweep_anchor_drift_px': max(
            # The car's own anchor, from the measured body boxes: the framing
            # solver pins it, and the wide footprints at large angles are the
            # wet-road response changing shape, which is reported separately.
            [abs(entry['centre_x'] - boxes_report['phases']['night']['0']
                 ['centre_x'])
             for angle, entry in boxes_report['phases']['night'].items()]
            + [abs(entry['contact_y'] - boxes_report['phases']['night']['0']
                   ['contact_y'])
               for angle, entry in boxes_report['phases']['night'].items()]),
        'yaw_sweep_footprint_drift_px': max(
            entry['box_centre_drift_px'] for entry in report['yaw_sweep'].values()),
        'band_shift_matches_declared': all(
            abs(report['motion'][str(speed)]['measured_band_shift_px']
                - report['motion'][str(speed)]['declared_parallax_near_px'])
            <= 2.0 for speed in (30, 80, 120)),
        'awareness_information_band_overlap_pixels': max(
            report['awareness'][f'{name}_{speed}']
            ['information_band_overlap_pixels']
            for name, _extra in AWARENESS_STATES for speed in (0, 80)),
        'phase_body_box_max_delta_px': {
            label: entry['phase_body_box_max_delta_px']
            for label, entry in report['scale_trials'].items()},
        'ui_pixels_changed_by_camera_yaw': int(changed(ui_zero, ui_fast).sum()),
        'awareness_mirror_max_channel_error': max(
            report['awareness'][f'mirror_{speed}']['max_channel_error']
            for speed in (0, 80)),
        'ghost_body_overlap_pixels': max(
            report['awareness'][f'ghost_body_overlap_{speed}']
            ['overlap_pixels'] for speed in (0, 80))}
    gates['yaw_continuous_full_curve'] = all(
        abs(motion.screen_motion_vector(speed + 1)['chase_yaw_deg']
            - motion.screen_motion_vector(speed)['chase_yaw_deg']) < 0.6
        for speed in range(0, 200))
    report['gates'] = gates
    (OUT / 'horizon_v55_chase_metrics.json').write_text(
        json.dumps(report, indent=1) + '\n')
    print(json.dumps({key: value for key, value in report.items()
                      if key in ('gates', 'yaw_sweep')}, indent=1)[:2000])
    print(f"[v5.5-chase] {os.path.relpath(OUT / 'horizon_v55_chase_metrics.json', ROOT)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
