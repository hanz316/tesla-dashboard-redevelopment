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


if __name__ == '__main__':
    unittest.main()
