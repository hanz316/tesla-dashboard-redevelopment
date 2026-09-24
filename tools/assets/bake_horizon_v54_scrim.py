#!/usr/bin/env python3
"""Bake the selected A treatment: one horizontal field, no radial masks."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]


def smooth(x):
    x = np.clip(x, 0, 1)
    return x*x*(3-2*x)


def field():
    y,x = np.mgrid[:480,:1920]
    outer = smooth((x-120)/160) * smooth((1800-x)/160)
    centre = 1-smooth((x-590)/190)*smooth((1320-x)/190)
    vertical = smooth((y-22)/115) * smooth((465-y)/120)
    return outer*centre*vertical


def main():
    alpha = field()
    pixels = np.zeros((480,1920,4),dtype=np.uint8)
    pixels[:,:,:3] = (235,240,244)
    # A restrained luminous scrim supports graphite ink without a dark bubble.
    pixels[:,:,3] = np.rint(alpha*36).astype(np.uint8)
    image = Image.fromarray(pixels)
    box = image.getchannel('A').getbbox()
    source = 'assets/ui/horizon_v54_surface_scrim.png'
    image.crop(box).save(ROOT/source)
    report = {'schema':'horizon-v5.4-scrim v1','candidates':{'scrim':{
        'file':source,'box':list(box),'peak_alpha':36,
        'decoded_rgba_bytes':(box[2]-box[0])*(box[3]-box[1])*4}},
        'centre_max_alpha':int(pixels[:,800:1120,3].max()),
        'max_adjacent_alpha_step':int(max(np.abs(np.diff(pixels[:,:,3].astype(int),axis=0)).max(),
                                        np.abs(np.diff(pixels[:,:,3].astype(int),axis=1)).max())),
        'phase_strength':{'day':1,'dawn':.25,'dusk':.25,'night':.03}}
    (ROOT/'assets/checkpoints/horizon_v54/scrim.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__ == '__main__':
    main()
