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
              'phases':{},'scale_trials':{},'blind_zone':{}}
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
    neutral_path = frame(scene, day_env, state, 'blind_neutral')
    neutral = np.asarray(Image.open(neutral_path).convert('RGB')).astype(np.int16)
    for name, fixture in (
            ('none', state),
            ('left', dict(state, blind_left=True)),
            ('right', dict(state, blind_right=True)),
            ('both', dict(state, blind_left=True, blind_right=True)),
            ('left_indicator', dict(state, blind_left=True, indicator_left=True)),
            ('right_indicator', dict(state, blind_right=True, indicator_right=True))):
        path = frame(scene, day_env, fixture, 'blind_' + name)
        current = np.asarray(Image.open(path).convert('RGB')).astype(np.int16)
        changed = np.max(np.abs(current-neutral), axis=2) > 5
        ys, xs = np.where(changed)
        box = [int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)] if xs.size else None
        report['blind_zone'][name] = {
            'changed_pixels': int(changed.sum()),
            'combined_box': box,
            'left_safe_zone_overlap_pixels': int(changed[:, 240:590].sum()),
            'right_safe_zone_overlap_pixels': int(changed[:, 1330:1720].sum()),
            'indicator_attention': name in ('left_indicator','right_indicator')}
    report['body_boxes_equal'] = report['phases']['day']['body_box']==report['phases']['night']['body_box']
    # Assess overlay symmetry on a common black backing; the daylight plate
    # has different radiance on each side and biases thresholded changed counts.
    blind_scene = dict(scene, nodes=[n for n in scene['nodes'] if n['id'].startswith('blind.')])
    left_path = frame(blind_scene, {}, {'blind_left': True}, 'blind_isolated_left')
    right_path = frame(blind_scene, {}, {'blind_right': True}, 'blind_isolated_right')
    empty_path = frame(blind_scene, {}, {}, 'blind_isolated_none')
    backing = np.asarray(Image.open(empty_path)).astype(int)
    left_pixels = np.asarray(Image.open(left_path)).astype(int) - backing
    right_pixels = (np.asarray(Image.open(right_path)).astype(int) - backing)[:, ::-1]
    report['blind_symmetry_max_channel_error'] = int(np.abs(left_pixels-right_pixels).max())
    report['body_box_max_delta_px'] = max(abs(a-b) for a,b in zip(
        report['phases']['day']['body_box'], report['phases']['night']['body_box']))
    report['body_footprint_within_raster_tolerance'] = report['body_box_max_delta_px'] <= 1
    report['selected_scale'] = json.loads((ROOT/'assets/ui/horizon_v54_presentation.json').read_text())['scale']
    (OUT/'metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key!='phases'},indent=2))

if __name__=='__main__':
    main()
