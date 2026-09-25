#!/usr/bin/env python3
"""Reproducible V5.4 pixel evidence. All state values are developer fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import scene_preview as preview
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'assets/checkpoints/horizon_v54'
VEHICLE = ROOT/'assets/rendered/vehicle/horizon_v5'


def lum(rgb):
    rgb = np.asarray(rgb,dtype=float)/255
    linear = np.where(rgb <= .04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    return (linear * np.array([.2126,.7152,.0722], dtype=np.float64)).sum(axis=2)


def half(path):
    out = path.with_name(path.stem+'_half.png')
    Image.open(path).resize((960,240),Image.Resampling.LANCZOS).save(out)
    return out


def pair(left,right,path):
    a,b = Image.open(left).convert('RGB'),Image.open(right).convert('RGB')
    image = Image.new('RGB',(a.width+b.width,max(a.height,b.height)))
    image.paste(a,(0,0));image.paste(b,(a.width,0));image.save(path)


def frame(scene,env,state,name):
    path = OUT/(name+'.png')
    preview.render(scene,None,state,str(path),t_norm=0,environment=env)
    half(path)
    return path


def material_stats(phase):
    mask = np.asarray(Image.open(VEHICLE/'day/material_mask.png').convert('RGBA'))
    root = VEHICLE if phase=='night' else VEHICLE/phase
    car = np.asarray(Image.open(root/'car/base/000.png').convert('RGBA'))
    classes = {'paint':[255,0,0],'glass':[0,255,0],'tyre':[0,0,255],'rim':[255,255,0]}
    result = {}
    brightness = (car[:,:,:3].astype(np.float32) *
                  np.array([.2126,.7152,.0722], dtype=np.float32)).sum(axis=2)
    for key,color in classes.items():
        selected = (np.abs(mask[:,:,:3].astype(float)-color).max(axis=2)<12)&(mask[:,:,3]>250)
        selected = np.asarray(Image.fromarray((selected*255).astype('uint8')).filter(ImageFilter.MinFilter(3)))>0
        values = brightness[selected]
        result[key] = {'pixels':int(values.size),'mean':round(float(values.mean()),2),
                       'p10_p50_p90':[round(float(v),2) for v in np.percentile(values,[10,50,90])]}
        box = Image.fromarray((selected*255).astype('uint8')).getbbox()
        if box:
            Image.fromarray(car).crop(box).save(OUT/f'{phase}_{key}_crop.png')
    result['glass_minus_paint'] = round(result['glass']['mean']-result['paint']['mean'],2)
    result['rim_minus_tyre'] = round(result['rim']['mean']-result['tyre']['mean'],2)
    return result


def contrast_stats(scene,env,state):
    result = {}
    ids = ('speed.value','energy.range','energy.soc','energy.power','speed.unit',
           'energy.range.label','energy.soc.label','energy.power.label','climate.status')
    for identity in ids:
        nodes = [n for n in scene['nodes'] if n['id']==identity]
        if not nodes: continue
        node = preview.apply_colour_map(nodes[0],env['colour_map'])
        node = dict(node,color=env['palette'].get(node.get('color_token'),node.get('color')))
        bgscene = dict(scene,nodes=[n for n in scene['nodes'] if n['id']!=identity])
        bgpath = OUT/'_contrast_background.png'
        preview.render(bgscene,None,state,str(bgpath),t_norm=0,environment=env)
        background = Image.open(bgpath).convert('RGBA')
        mask = Image.new('RGBA',(1920,480))
        preview.draw_text(mask,dict(node,color='#FFFFFF',shadow=False),preview.State(state))
        foreground = background.copy()
        preview.draw_text(foreground,node,preview.State(state))
        entry = {}
        for label,size in [('full',(1920,480)),('half',(960,240))]:
            m = np.asarray(mask.resize(size,Image.Resampling.LANCZOS))[:,:,3]
            a = lum(np.asarray(foreground.resize(size,Image.Resampling.LANCZOS))[:,:,:3])
            b = lum(np.asarray(background.resize(size,Image.Resampling.LANCZOS))[:,:,:3])
            selected = m >= (180 if label=='full' else 130)
            ratio = (np.maximum(a,b)+.05)/(np.minimum(a,b)+.05)
            values = ratio[selected]
            entry[label] = {'ink_pixels':int(values.size),
                            'median_ratio':round(float(np.median(values)),2),
                            'p10_ratio':round(float(np.percentile(values,10)),2)}
        result[identity] = entry
    (OUT/'_contrast_background.png').unlink(missing_ok=True)
    return result


def main():
    OUT.mkdir(exist_ok=True)
    scene = json.loads((ROOT/'scenes/horizon_v5.scene').read_text())
    # Clock fixture prevents time passing from polluting comparisons.
    for node in scene['nodes']:
        if node['id']=='top.clock':
            node.pop('source',None);node['text']='13:51'
    tokens = preview.tokens_document(scene)
    state = copy.deepcopy(preview.MOCK_STATES['v5_neutral'])
    report = {'schema':'horizon-v5.4-evidence v1','measurement_platform':'MAC MEASURED',
              'device':'UNKNOWN_UNTIL_DEVICE_TEST','state_source':'DEVELOPER_FIXTURE',
              'phases':{},'scale_trials':{},'awareness_zone':{}}
    for phase in ('day','night'):
        env = preview.environment_context(tokens,phase=phase)
        path = frame(scene,env,state,'after_'+phase)
        pair(OUT/f'before_{phase}.png',path,OUT/f'before_after_{phase}.png')
        pair(half(OUT/f'before_{phase}.png'),half(path),OUT/f'before_after_{phase}_half.png')
        plate = ROOT/env['plate']
        Image.open(plate).save(OUT/f'after_environment_{phase}.png')
        pair(OUT/f'before_environment_{phase}.png',plate,OUT/f'environment_before_after_{phase}.png')
        root = VEHICLE if phase=='night' else VEHICLE/phase
        car = Image.open(root/'car/base/000.png').convert('RGBA')
        car.save(OUT/f'after_vehicle_{phase}.png')
        pair(OUT/f'before_vehicle_{phase}.png',OUT/f'after_vehicle_{phase}.png',OUT/f'vehicle_before_after_{phase}.png')
        body = car.getchannel('A').getbbox()
        # Measure each phase independently. Reusing DAY's camera report for
        # NIGHT would make equality tautological and conceal a scale defect.
        layer = env['vehicle']['base']
        rgba = Image.open(layer['source']).convert('RGBA')
        tight = rgba.getchannel('A').getbbox()
        global_box = [tight[i]+layer['offset'][i%2] for i in range(4)]
        presentation = json.loads((ROOT/'assets/ui/horizon_v54_presentation.json').read_text())
        px,py,pw,ph = preview.presentation_bounds(body[0],body[1],body[2]-body[0],body[3]-body[1],presentation)
        entry = {'body_box':list(body), 'presented_body_box':[px,py,px+pw,py+ph],
                 'alpha_pixels':int((np.asarray(car)[:,:,3]>0).sum()),
                 'combined_layer_box':global_box,'material_classes':material_stats(phase),
                 'contrast':contrast_stats(scene,env,state),
                 'plate_sha256':hashlib.sha256(plate.read_bytes()).hexdigest(),
                 'base_layer_decoded_bytes':rgba.width*rgba.height*4}
        report['phases'][phase] = entry
        for scale in (1.06,1.09,1.12):
            trial = copy.deepcopy(scene)
            for node in trial['nodes']:
                if 'presentation' in node: node['presentation']['scale']=scale
            frame(trial,env,state,f'{phase}_scale_{round((scale-1)*100):02d}')
            x,y,w,h = preview.presentation_bounds(body[0],body[1],body[2]-body[0],body[3]-body[1],
                                                  {'scale':scale,'anchor':[954,345]})
            report['scale_trials'].setdefault(str(scale),{})[phase] = {
                'body_box':[x,y,x+w,y+h],'body_width':w,
                'safe_zone_clearance':[x-672,1248-(x+w)]}
    day_env = preview.environment_context(tokens, phase='day')
    layout = json.loads((ROOT/'assets/ui/horizon_v5_layout.json').read_text())
    zones = layout['zones']
    band_left = min(zone['x'] for zone in zones.values())
    band_right = max(zone['right'] for zone in zones.values())
    report['information_band_px'] = [band_left, band_right]
    # The peripheral zone columns come from the layout the runtime uses, so the
    # gate cannot drift away from where the zones actually are.
    zone_window = {}
    for component in layout['components']:
        identity = component['id'].split('.')
        if len(identity) == 3 and identity[0] == 'awareness' \
                and identity[2] in ('green', 'amber', 'red'):
            bounds = component['bounds']
            window = zone_window.setdefault(
                identity[1], [bounds['x'], bounds['x'] + bounds['w']])
            window[0] = min(window[0], bounds['x'])
            window[1] = max(window[1], bounds['x'] + bounds['w'])
    report['awareness_zone_columns'] = zone_window
    # Every state is measured on the awareness layer alone. Measuring against
    # the whole panel would fold the turn-lamp pixels, the streaks and the
    # vehicle layers into the numbers and hide what this layer itself does.
    zone_scene = dict(scene, nodes=[
        node for node in scene['nodes']
        if node['id'].startswith('awareness.')
        and not node['id'].endswith('.ghost')])
    layer_scene = dict(scene, nodes=[
        node for node in scene['nodes'] if node['id'].startswith('awareness.')])
    ghost_scene = dict(scene, nodes=[
        node for node in scene['nodes']
        if node['id'].startswith('awareness.') and node['id'].endswith('.ghost')])
    neutral_path = frame(zone_scene, day_env, state, 'awareness_neutral')
    neutral = np.asarray(Image.open(neutral_path).convert('RGB')).astype(np.int16)

    def changed_against_neutral(path):
        current = np.asarray(Image.open(path).convert('RGB')).astype(np.int16)
        return np.max(np.abs(current-neutral), axis=2) > 5

    def side_leak(changed, side):
        other = 'right' if side == 'left' else 'left'
        window = zone_window[other]
        return int(changed[:, window[0]:window[1]].sum())

    # The zone colour is a state selection, not a run-time tint, so every
    # semantic state is measured from the pixels that state actually produces.
    fixtures = (
        ('none', {}, 'none', None),
        ('left_presence', {'blind_left': True}, 'left/amber', 'left'),
        ('right_presence', {'blind_right': True}, 'right/amber', 'right'),
        ('both_presence', {'blind_left': True, 'blind_right': True},
         'both/amber', None),
        ('left_turn', {'indicator_left': True, 'blind_left': False},
         'left/green', 'left'),
        ('right_turn', {'indicator_right': True, 'blind_right': False},
         'right/green', 'right'),
        ('left_conflict', {'blind_left': True, 'indicator_left': True},
         'left/red', 'left'),
        ('right_conflict', {'blind_right': True, 'indicator_right': True},
         'right/red', 'right'),
        ('hazards_clear', {'hazards': True, 'blind_left': False,
                           'blind_right': False}, 'both/green', None),
        ('hazards_conflict', {'blind_left': True, 'blind_right': True,
                              'hazards': True}, 'both/red', None),
        # Turn intent with no presence reading does not claim a clear side.
        ('left_turn_unconfirmed', {'indicator_left': True}, 'suppressed', None))
    support = {}
    for name, extra, semantic, own_side in fixtures:
        path = frame(zone_scene, day_env, dict(state, **extra),
                     'awareness_' + name)
        changed = changed_against_neutral(path)
        support[name] = changed
        ys, xs = np.where(changed)
        box = [int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)] \
            if xs.size else None
        entry = {
            'semantic': semantic,
            'changed_pixels': int(changed.sum()),
            'combined_box': box,
            'information_band_overlap_pixels':
                int(changed[:, band_left:band_right].sum()),
            'opposite_side_zone_leak_pixels':
                side_leak(changed, own_side) if own_side else None}
        if own_side:
            window = zone_window[own_side]
            entry['own_side_zone_pixels'] = int(
                changed[:, window[0]:window[1]].sum())
        report['awareness_zone'][name] = entry
    # UNKNOWN, stale and invented presence must not paint a zone at all.
    suppression = {}
    for label, value in (('unknown', {'value': True, 'valid': False}),
                         ('stale', {'value': True, 'valid': True,
                                    'stale': True}),
                         ('synthetic', False)):
        path = frame(zone_scene, day_env, dict(state, blind_left=value),
                     'awareness_suppressed_' + label)
        current = np.asarray(Image.open(path).convert('RGB')).astype(np.int16)
        suppression[label] = int(np.abs(current-neutral).max())
    report['awareness_suppression_max_channel_delta'] = suppression
    # The colour is a state selection over one shared field, so the artwork
    # itself has to prove it: same alpha, different colour, exact mirror.
    def rgba(path):
        return np.asarray(Image.open(path).convert('RGBA')).astype(int)
    assets = {}
    for side in ('left', 'right'):
        layers = {name: rgba(ROOT/f'assets/ui/horizon_v54_zone_{side}_{name}.png')
                  for name in ('green', 'amber', 'red')}
        names = sorted(layers)
        assets[side] = {
            'alpha_equal_across_colours': all(np.array_equal(
                layers[names[0]][:, :, 3], layers[name][:, :, 3])
                for name in names[1:]),
            'colour_min_channel_separation': int(min(
                np.abs(layers[a][:, :, :3] - layers[b][:, :, :3]).max()
                for index, a in enumerate(names) for b in names[index+1:])),
            'mirror_max_channel_error': int(np.abs(
                layers['amber'] -
                rgba(ROOT/f'assets/ui/horizon_v54_zone_'
                     f'{"right" if side == "left" else "left"}_amber.png'
                     )[:, ::-1]).max())}
    ghost = rgba(ROOT/'assets/ui/horizon_v54_ghost_left.png')
    ghost_right = rgba(ROOT/'assets/ui/horizon_v54_ghost_right.png')
    assets['ghost'] = {
        'max_alpha_gradient': int(max(
            np.abs(np.diff(ghost[:, :, 3], axis=1)).max(),
            np.abs(np.diff(ghost[:, :, 3], axis=0)).max())),
        'mirror_max_channel_error': int(np.abs(ghost - ghost_right[:, ::-1]).max())}
    report['awareness_assets'] = assets
    # The secondary silhouette is a separate promise: it is soft, it sits on
    # the present side only, and conflict raises it without ever making it the
    # thing that carries the warning.
    ghost_neutral = np.asarray(Image.open(frame(
        ghost_scene, day_env, state, 'awareness_ghost_neutral')).convert('RGB'))
    ghost_state = {}
    for label, extra in (('presence', {'blind_left': True}),
                         ('conflict', {'blind_left': True,
                                       'indicator_left': True})):
        ghost_frame = np.asarray(Image.open(frame(
            ghost_scene, day_env, dict(state, **extra),
            f'awareness_ghost_{label}')).convert('RGB')).astype(int)
        delta = np.max(np.abs(ghost_frame - ghost_neutral), axis=2)
        ys, xs = np.nonzero(delta > 5)
        ghost_state[label] = {
            'changed_pixels': int((delta > 5).sum()),
            'combined_box': [int(xs.min()), int(ys.min()), int(xs.max()+1),
                             int(ys.max()+1)] if xs.size else None,
            'other_side_changed_pixels': int((delta[:, 960:] > 5).sum())}
    ghost_presence = np.asarray(Image.open(
        OUT/'awareness_ghost_presence.png').convert('RGB')).astype(int)
    ghost_conflict = np.asarray(Image.open(
        OUT/'awareness_ghost_conflict.png').convert('RGB')).astype(int)
    ghost_state['conflict_minus_presence_max_channel_delta'] = int(
        np.abs(ghost_conflict - ghost_presence).max())
    report['awareness_ghost'] = ghost_state
    # And the renderer has to show that selection: presence, conflict and turn
    # change the pixels without one of them being a tinted copy of another's
    # geometry, and the opposite indicator never repaints the present side.
    def rendered(name):
        return np.asarray(Image.open(OUT/f'awareness_{name}.png')
                          .convert('RGB')).astype(np.int16)
    semantics = {}
    for side in ('left', 'right'):
        other = 'right' if side == 'left' else 'left'
        presence = rendered(f'{side}_presence')
        conflict = rendered(f'{side}_conflict')
        turn = rendered(f'{side}_turn')
        opposite = frame(zone_scene, day_env,
                         dict(state, **{f'blind_{side}': True,
                                        f'indicator_{other}': True,
                                        f'blind_{other}': False}),
                         f'awareness_{side}_presence_opposite_turn')
        opposite_pixels = np.asarray(Image.open(opposite).convert('RGB')).astype(int)
        own_window = zone_window[side]
        other_window = zone_window[other]
        opposite_delta = np.max(np.abs(opposite_pixels - presence), axis=2)
        # Presence and conflict select the same field. The only pixels that may
        # differ are where the faint fringe falls under the measurement
        # threshold, because the amber and red values are not equally bright;
        # the overlap records exactly how much of the field is shared.
        presence_support = support[f'{side}_presence']
        conflict_support = support[f'{side}_conflict']
        union = int((presence_support | conflict_support).sum())
        semantics[side] = {
            'presence_vs_conflict_support_difference_pixels': int(
                (presence_support != conflict_support).sum()),
            'presence_vs_conflict_support_overlap_ratio': round(
                int((presence_support & conflict_support).sum()) /
                max(1, union), 4),
            'presence_vs_conflict_max_channel_delta':
                int(np.abs(presence - conflict).max()),
            'turn_vs_presence_support_difference_pixels': int(
                (support[f'{side}_turn'] != support[f'{side}_presence']).sum()),
            'presence_vs_turn_max_channel_delta': int(np.abs(presence - turn).max()),
            'opposite_turn_repaints_present_side_pixels': int(
                (opposite_delta[:, own_window[0]:own_window[1]] > 5).sum()),
            'opposite_turn_paints_other_side_pixels': int(
                (opposite_delta[:, other_window[0]:other_window[1]] > 5).sum())}
    report['awareness_semantics'] = semantics
    report['body_boxes_equal'] = report['phases']['day']['body_box']==report['phases']['night']['body_box']
    # Assess overlay symmetry on a common black backing; the daylight plate
    # has different radiance on each side and biases thresholded changed counts.
    awareness_scene = dict(scene, nodes=[n for n in scene['nodes']
                                         if n['id'].startswith('awareness.')])
    left_path = frame(awareness_scene, {}, {'blind_left': True},
                      'awareness_isolated_left')
    right_path = frame(awareness_scene, {}, {'blind_right': True},
                       'awareness_isolated_right')
    empty_path = frame(awareness_scene, {}, {}, 'awareness_isolated_none')
    backing = np.asarray(Image.open(empty_path)).astype(int)
    left_pixels = np.asarray(Image.open(left_path)).astype(int) - backing
    right_pixels = (np.asarray(Image.open(right_path)).astype(int) - backing)[:, ::-1]
    report['awareness_symmetry_max_channel_error'] = int(np.abs(left_pixels-right_pixels).max())
    report['body_box_max_delta_px'] = max(abs(a-b) for a,b in zip(
        report['phases']['day']['body_box'], report['phases']['night']['body_box']))
    report['body_footprint_within_raster_tolerance'] = report['body_box_max_delta_px'] <= 1
    report['selected_scale'] = json.loads((ROOT/'assets/ui/horizon_v54_presentation.json').read_text())['scale']
    (OUT/'metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key!='phases'},indent=2))

if __name__=='__main__':
    main()
