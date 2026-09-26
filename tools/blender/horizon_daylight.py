"""Offline daylight rig for the frozen Model A. No runtime geometry or blur.

World direction, metre-scale asphalt and depth-bearing terrain replace the
night rig's flat daylight wash. Material edits are in-memory, never saved over
an approved master. Geometry, camera and lamp ownership remain untouched.
"""
import math
import bpy


def world(scene):
    sky = bpy.data.worlds.new('V54_Overcast')
    sky.use_nodes = True
    scene.world = sky
    tree = sky.node_tree
    tree.nodes.clear()
    out = tree.nodes.new('ShaderNodeOutputWorld')
    coord = tree.nodes.new('ShaderNodeTexCoord')
    xyz = tree.nodes.new('ShaderNodeSeparateXYZ')
    tree.links.new(coord.outputs['Normal'], xyz.inputs[0])
    # Elevation in world space: lower hemisphere stays dark to give metal its
    # ground response, horizon is warm-neutral, upper sky cool blue-grey.
    remap = tree.nodes.new('ShaderNodeMapRange')
    remap.inputs['From Min'].default_value = 1
    remap.inputs['From Max'].default_value = -1
    tree.links.new(xyz.outputs['Z'], remap.inputs['Value'])
    ramp = tree.nodes.new('ShaderNodeValToRGB')
    # Measured complaint: "flat grey atmosphere". The horizon band stays warm
    # and the zenith is a deeper blue, so the sky itself carries a gradient the
    # car can reflect; the previous ramp was nearly one value across the sky.
    stops = [(0, (.022,.028,.036,1)), (.48,(.11,.14,.17,1)),
             (.5,(.82,.82,.78,1)), (.55,(.44,.56,.70,1)),
             (.65,(.22,.34,.52,1)), (1,(.40,.54,.72,1))]
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[0].color = stops[0]
    for pos, col in stops[1:]:
        ramp.color_ramp.elements.new(pos).color = col
    ramp.color_ramp.interpolation = 'EASE'
    tree.links.new(remap.outputs['Result'], ramp.inputs[0])
    bg = tree.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = 1.1
    tree.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    tree.links.new(bg.outputs[0], out.inputs[0])


def asphalt(plane):
    tree = plane.data.materials[0].node_tree
    geometry = tree.nodes.new('ShaderNodeNewGeometry')
    # Generated coordinates normalise a 9 km plane: under the car they are
    # virtually constant. Position gives roughness/albedo a physical scale.
    for node in list(tree.nodes):
        if node.bl_idname == 'ShaderNodeTexNoise':
            tree.links.new(geometry.outputs['Position'], node.inputs['Vector'])
    shader = next(n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED')
    shader.inputs['Specular IOR Level'].default_value = .3
    for node in tree.nodes:
        if node.type == 'BUMP':
            # Measured complaint: "the road looks synthetic". A flat fill reads
            # as synthetic however smooth it is, so the metre-scale relief is
            # stronger here than in the night pass.
            node.inputs['Distance'].default_value = .012
            node.inputs['Strength'].default_value = .28


def terrain(scene, spec, place, frame):
    made = []
    for index, layer in enumerate(spec['ridges']):
        columns, rows = 320, 26
        vertices, faces = [], []
        for row in range(rows):
            depth = row / (rows-1)
            for col in range(columns):
                t = col / (columns-1)
                u = (t-.5)*layer['width']
                crest = (.5+.24*math.sin(t*math.pi*layer['freq']+layer['phase'])
                         +.16*math.sin(t*math.pi*19+index)
                         +.075*math.sin(t*math.pi*57+index*2)
                         +.032*math.sin(t*math.pi*123))
                slope = math.sin(math.pi*depth) ** 1.3
                folds = .88+.12*math.sin(t*90+depth*15)
                z = max(0,layer['height']*crest*slope*folds)
                vertices.append(tuple(place(u+layer['u'],
                    layer['v']+(depth-.5)*layer['height']*7,z)))
        for row in range(rows-1):
            for col in range(columns-1):
                a = row*columns+col
                faces.append((a,a+1,a+columns+1,a+columns))
        mesh = bpy.data.meshes.new(f'V5_Terrain_{index}')
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(mesh.name,mesh)
        scene.collection.objects.link(obj)
        for poly in mesh.polygons:
            poly.use_smooth = True
        mat = bpy.data.materials.new(mesh.name+'_M')
        mat.use_nodes = True
        tree = mat.node_tree
        shader = tree.nodes.get('Principled BSDF')
        shader.inputs['Roughness'].default_value = 1
        shader.inputs['Base Color'].default_value = layer['colour']
        tex = tree.nodes.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value = 8
        tex.inputs['Detail'].default_value = 5
        ramp = tree.nodes.new('ShaderNodeValToRGB')
        base = layer['colour']
        # Measured complaint: "low cinematic depth" - the ridge line carried a
        # 3.35 level edge. More albedo contrast inside each layer plus a sharper
        # crest gives the silhouette something to read.
        ramp.color_ramp.elements[0].color = tuple(c*.45 for c in base[:3])+(1,)
        ramp.color_ramp.elements[1].color = base
        tree.links.new(tex.outputs['Fac'],ramp.inputs[0])
        tree.links.new(ramp.outputs[0],shader.inputs['Base Color'])
        # Aerial perspective gets weaker towards the foreground. Unlike the
        # old phase merge this haze is not erased by ridge_emit_scale=0.
        shader.inputs['Emission Color'].default_value = (.43,.52,.59,1)
        shader.inputs['Emission Strength'].default_value = (.30,.16,.06)[index]
        obj.data.materials.append(mat)
        made.append(obj)
    return made


def materials():
    changes = {}
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        shader = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'),None)
        if shader is None:
            continue
        values = {}
        if mat.name.startswith('M_Paint'):
            values = {'Metallic':.85,'Roughness':.20,'Coat Weight':.58,
                      'Coat Roughness':.10}
        elif mat.name.startswith('M_Glass'):
            values = {'Base Color':(.008,.015,.021,1),'Roughness':.12,
                      'Specular IOR Level':.32,'Transmission Weight':.03,'IOR':1.45}
        elif mat.name.startswith('M_Tire'):
            values = {'Base Color':(.004,.005,.006,1),'Roughness':.91,
                      'Specular IOR Level':.18}
        elif mat.name.startswith('M_Wheel'):
            values = {'Metallic':.88,'Roughness':.3}
        if mat.name.startswith('M_Glass'):
            for node in mat.node_tree.nodes:
                if node.type == 'MIX_SHADER':
                    node.inputs[0].default_value = .075
                if node.type == 'BSDF_GLOSSY':
                    node.inputs['Color'].default_value = (.22,.28,.34,1)
                    node.inputs['Roughness'].default_value = .055
        if mat.name.startswith('M_Paint'):
            # Preserve the subtle flake normal, but tame its exaggerated scale.
            for node in mat.node_tree.nodes:
                if node.type == 'BUMP':
                    node.inputs['Distance'].default_value = .00025
                    node.inputs['Strength'].default_value = .12
            for link in list(shader.inputs['Roughness'].links):
                mat.node_tree.links.remove(link)
        for key,value in values.items():
            shader.inputs[key].default_value = value
        if values:
            changes[mat.name] = values
    return changes


def material_mask(scene, objects, path):
    """Ground-truth material classes, not percentile guesses of brightness."""
    colours = {'paint':(1,0,0,1),'glass':(0,1,0,1),
               'tyre':(0,0,1,1),'rim':(1,1,0,1),'other':(0,1,1,1)}
    masks = {}
    for name, colour in colours.items():
        mat = bpy.data.materials.new('V54_Mask_'+name)
        mat.use_nodes = True
        tree = mat.node_tree
        tree.nodes.clear()
        output = tree.nodes.new('ShaderNodeOutputMaterial')
        emission = tree.nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value = colour
        tree.links.new(emission.outputs[0],output.inputs[0])
        masks[name] = mat
    assignment = {}
    for obj in objects:
        for index, mat in enumerate(obj.data.materials):
            name = 'other'
            if mat:
                for prefix, group in [('M_Paint','paint'),('M_Glass','glass'),
                                      ('M_Tire','tyre'),('M_Wheel','rim')]:
                    if mat.name.startswith(prefix):
                        name = group
                        break
                assignment[mat.name] = name
            obj.data.materials[index] = masks[name]
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.cycles.samples = 1
    scene.cycles.use_denoising = False
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return {'colours':colours,'assignment':assignment}
