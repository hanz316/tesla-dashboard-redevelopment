"""Pixel regressions for crop placement, phase alpha and state visibility."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/preview'))
import scene_preview as preview


class PhaseCompositingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def entry(self, name, offset, size, box, color):
        image = Image.new('RGBA', size)
        from PIL import ImageDraw
        ImageDraw.Draw(image).rectangle(box, fill=color)
        path = self.root/(name+'.png')
        image.save(path)
        return {'source':str(path),'offset':offset,'size':size}

    def test_crop_margins_never_rescale_body(self):
        a = self.entry('night',[10,10],[40,30],[10,5,29,24],(100,120,140,255))
        b = self.entry('day',[15,5],[60,45],[5,10,24,29],(200,210,220,255))
        for t in [0,.001,.25,.5,.75,.999,1]:
            image,origin = preview.blend_vehicle_layers(a,b,t)
            box = image.getchannel('A').getbbox()
            self.assertEqual(tuple(box[i]+origin[i%2] for i in range(4)),(20,15,40,35))
            self.assertEqual(image.getpixel((15,15))[3],255)

    def test_transparent_rgb_does_not_leak_into_crossfade(self):
        a = self.entry('a',[0,0],[4,4],[0,0,3,3],(255,0,0,0))
        b = self.entry('b',[0,0],[4,4],[0,0,3,3],(0,100,200,255))
        image,_ = preview.blend_vehicle_layers(a,b,.5)
        self.assertEqual(image.getpixel((1,1)),(0,100,200,128))

    def test_phase_replacement_obeys_lamp_visibility(self):
        layer = self.entry('lamp',[10,10],[8,8],[0,0,7,7],(255,0,0,255))
        node = {'id':'vehicle.brake','type':'image','alpha':0,
                'alpha_when':[{'when':{'bind':'brake','eq':True},'alpha':1}]}
        scene = {'canvas':{'width':32,'height':32},'nodes':[node]}
        # Use the exact compiler-emitted condition, rather than duplicating it.
        actual = json.loads((ROOT/'scenes/horizon_v5.scene').read_text())
        node['alpha_when'] = next(n for n in actual['nodes'] if n['id']=='vehicle.brake')['alpha_when']
        for state in ({'brake':False},{}, {'brake':{'value':True,'valid':False}}):
            path = self.root/'off.png'
            preview.render(scene,None,state,str(path),environment={'vehicle':{'brake':layer}})
            self.assertEqual(Image.open(path).getpixel((12,12)),(0,0,0))
        path = self.root/'on.png'
        preview.render(scene,None,{'brake':True},str(path),environment={'vehicle':{'brake':layer}})
        self.assertEqual(Image.open(path).getpixel((12,12)),(255,0,0))

    def test_manifest_dimensions_are_checked(self):
        a = self.entry('a',[0,0],[4,4],[0,0,3,3],(1,2,3,255))
        a['size'] = [8,8]
        with self.assertRaises(ValueError):
            preview.blend_vehicle_layers(a,a,0)

    def test_conditional_palette_mapping_does_not_mutate_semantic_colors(self):
        node = {'color_when': [
            {'when': {'always': True}, 'color': '#E8EDF2'},
            {'when': {'always': True}, 'color': '#D8A657'}]}
        mapped = preview.apply_colour_map(node, {'#E8EDF2': '#293843'})
        self.assertEqual(mapped['color_when'][0]['color'], '#293843')
        self.assertEqual(mapped['color_when'][1]['color'], '#D8A657')
        self.assertEqual(node['color_when'][0]['color'], '#E8EDF2')

    def test_mono_day_and_night_map_background_with_text(self):
        import numpy as np
        scene = json.loads((ROOT/'scenes/v6_mono.scene').read_text())
        # No clock/labels: isolate speed against its own background.
        scene['nodes'] = [n for n in scene['nodes'] if n['id'] in ('bg','speed.value')]
        for phase in ('day','night'):
            for state in ({'speed': 88}, {}):
                path = self.root/'mono.png'
                preview.render(scene,None,state,str(path),environment=preview.environment_context({},phase=phase))
                frame = Image.open(path)
                for size in ((1920,480),(960,240)):
                    a = np.asarray(frame.resize(size)).astype(float)/255
                    linear = np.where(a <= .04045,a/12.92,((a+.055)/1.055)**2.4)
                    lum = (linear*[.2126,.7152,.0722]).sum(axis=2)
                    bg = lum[size[1]//5,size[0]//2]
                    ratio = (np.maximum(lum,bg)+.05)/(np.minimum(lum,bg)+.05)
                    centre = ratio[size[1]//4:size[1]*3//5,size[0]*43//100:size[0]*57//100]
                    self.assertGreater(np.percentile(centre,98),4.5, (phase,state,size))

    def test_stale_fixture_and_panel_aggregation_preserve_unknown(self):
        state = preview.State(preview.MOCK_STATES['v5_stale'])
        self.assertFalse(state.signal('speed').valid)
        self.assertFalse(state.signal('headlight').valid)
        state = preview.State({'door_fl': {'value': False, 'valid': True}})
        self.assertFalse(state.signal('any_door_open').valid)
        self.assertFalse(state.signal('any_door_open').value)
        state = preview.State({'door_fl': {'value': True, 'valid': True}})
        self.assertTrue(state.signal('any_door_open').valid)
        self.assertTrue(state.signal('any_door_open').value)

    def test_phase_document_matches_shared_time_source(self):
        sys.path.insert(0, str(ROOT/'tools/assets'))
        import horizon_v5_environment_time as time_system
        document = json.loads((ROOT/'assets/ui/horizon_v5_environment.json').read_text())
        self.assertEqual(document['palettes'], time_system.PALETTES)

    def test_every_motion_curve_is_zero_at_standstill(self):
        scene = json.loads((ROOT/'scenes/horizon_v5.scene').read_text())
        for node in scene['nodes']:
            if node['id'].startswith('motion.'):
                for key in ('opacity_from', 'crop_from', 'offset_from'):
                    if key in node:
                        self.assertEqual(preview.points_interp(node[key]['points'],0),0,node['id'])


if __name__ == '__main__':
    unittest.main()
