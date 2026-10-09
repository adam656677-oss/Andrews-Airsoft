"""Unique texture baking for props / hero structures.

Each material slot of a piece gets a layered *recipe* shader built from the
tileable library (sampled through the 'UVTex' real-world UV map) plus
curvature edge wear, cavity dirt, ground grime and streaks. Everything is
then baked (Cycles, CPU) into one texture set on the 'UVMap' layout:
  pass 1  AUX  = AO (R) + edge/curvature (G)    -> ray traced once
  pass 2  BC, ORM, M (emission, 1 spp)          -> AUX read back as an image
  pass 3  N (tangent, DirectX swizzle)
"""
import os

import bpy

from . import bl

SOCK_A, SOCK_B, SOCK_OUT = 6, 7, 2  # ShaderNodeMix RGBA sockets


class NB:
    def __init__(self, nt):
        self.nt = nt
        self.N = nt.nodes
        self.L = nt.links

    def node(self, t, **kw):
        n = self.N.new(t)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.L.new(a, b)

    def val(self, v):
        n = self.node('ShaderNodeValue')
        n.outputs[0].default_value = v
        return n.outputs[0]

    def rgb(self, c):
        n = self.node('ShaderNodeRGB')
        n.outputs[0].default_value = tuple(c) + (1,)
        return n.outputs[0]

    def math(self, op, a, b=None, clamp=False):
        n = self.node('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                self.link(x, n.inputs[i])
        return n.outputs[0]

    def mix(self, a, b, f, blend='MIX'):
        n = self.node('ShaderNodeMix', data_type='RGBA', blend_type=blend)
        for sock, x in ((SOCK_A, a), (SOCK_B, b)):
            if isinstance(x, (tuple, list)):
                n.inputs[sock].default_value = tuple(x) + (1,) if len(x) == 3 else tuple(x)
            else:
                self.link(x, n.inputs[sock])
        if isinstance(f, (int, float)):
            n.inputs['Factor'].default_value = f
        else:
            self.link(f, n.inputs['Factor'])
        return n.outputs[SOCK_OUT]

    def mixf(self, a, b, f):
        n = self.node('ShaderNodeMix', data_type='FLOAT')
        for i, x in ((2, a), (3, b)):
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                self.link(x, n.inputs[i])
        if isinstance(f, (int, float)):
            n.inputs['Factor'].default_value = f
        else:
            self.link(f, n.inputs['Factor'])
        return n.outputs[0]

    def mixv(self, a, b, f):
        n = self.node('ShaderNodeMix', data_type='VECTOR')
        self.link(a, n.inputs[4])
        self.link(b, n.inputs[5])
        if isinstance(f, (int, float)):
            n.inputs['Factor'].default_value = f
        else:
            self.link(f, n.inputs['Factor'])
        return n.outputs[1]

    def ramp(self, x, p0, p1):
        """smoothstep-like remap of scalar x from [p0,p1] to [0,1]."""
        n = self.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP', clamp=True)
        self.link(x, n.inputs['Value'])
        n.inputs['From Min'].default_value = p0
        n.inputs['From Max'].default_value = p1
        return n.outputs['Result']

    def noise(self, scale, detail=6, rough=0.6, vec=None, stretch=None, dist=0.0):
        n = self.node('ShaderNodeTexNoise')
        n.inputs['Scale'].default_value = scale
        n.inputs['Detail'].default_value = detail
        n.inputs['Roughness'].default_value = rough
        n.inputs['Distortion'].default_value = dist
        if vec is None:
            tc = self.node('ShaderNodeTexCoord')
            vec = tc.outputs['Object']
        if stretch is not None:
            mp = self.node('ShaderNodeMapping')
            mp.inputs['Scale'].default_value = stretch
            self.link(vec, mp.inputs['Vector'])
            vec = mp.outputs['Vector']
        self.link(vec, n.inputs['Vector'])
        return n.outputs['Fac']

    def lib(self, mat_id, scale=1.0, uv='UVTex', rot=0.0):
        """Library texture set sampled via a real-world UV map."""
        tile = bl.lib_tile(mat_id)
        p = bl.lib_paths(mat_id)
        uvn = self.node('ShaderNodeUVMap', uv_map=uv)
        mp = self.node('ShaderNodeMapping')
        s = scale / tile
        mp.inputs['Scale'].default_value = (s, s, 1)
        mp.inputs['Rotation'].default_value = (0, 0, rot)
        self.link(uvn.outputs['UV'], mp.inputs['Vector'])
        out = {}
        for k, nc in (('BC', False), ('ORM', True), ('N', True)):
            t = self.node('ShaderNodeTexImage')
            t.image = bl.load_image(p[k], nc)
            self.link(mp.outputs['Vector'], t.inputs['Vector'])
            out[k] = t
        sep = self.node('ShaderNodeSeparateColor')
        self.link(out['ORM'].outputs['Color'], sep.inputs['Color'])
        return {'bc': out['BC'].outputs['Color'], 'ao': sep.outputs[0], 'rough': sep.outputs[1],
                'metal': sep.outputs[2], 'n': bl.dx_normal_node(self.nt, out['N'], uv)}


def recipe_material(name, r):
    """Build a bake-ready material from a recipe dict. Returns material.

    recipe keys: base, scale, tint, rough_add, rough_mul, metal (override),
    paint (rgb) + chip (0..1) + paint_rough, under (lib id shown in chips),
    edge (amount of edge brightening), edge_col, dirt (cavity), dirt_col,
    ground (grime height m), streak (0..1), streak_col, mask (rgb role mask),
    nstr (normal strength), bump (procedural bump strength), wet.
    """
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    b = NB(nt)
    out = b.node('ShaderNodeOutputMaterial')
    bsdf = b.node('ShaderNodeBsdfPrincipled')
    b.link(bsdf.outputs[0], out.inputs['Surface'])
    emit = b.node('ShaderNodeEmission')
    emit.name = 'BAKE_EMIT'

    # AUX source (AO, edge) - replaced by baked image after pass 1
    ao = b.node('ShaderNodeAmbientOcclusion', samples=8, only_local=False)
    ao.inputs['Distance'].default_value = r.get('ao_dist', 0.25)
    bev = b.node('ShaderNodeBevel', samples=6)
    bev.inputs['Radius'].default_value = r.get('edge_r', 0.008)
    geo = b.node('ShaderNodeNewGeometry')
    dot = b.node('ShaderNodeVectorMath', operation='DOT_PRODUCT')
    b.link(bev.outputs[0], dot.inputs[0])
    b.link(geo.outputs['Normal'], dot.inputs[1])
    edge_raw = b.math('SUBTRACT', 1.0, dot.outputs['Value'], clamp=True)
    edge_raw = b.math('MULTIPLY', edge_raw, 6.0, clamp=True)
    auxc = b.node('ShaderNodeCombineColor')
    auxc.name = 'AUX_COMBINE'
    b.link(ao.outputs['Color'], auxc.inputs[0]) if False else b.link(ao.outputs['AO'], auxc.inputs[0])
    b.link(edge_raw, auxc.inputs[1])
    auxsrc = b.node('ShaderNodeSeparateColor')
    auxsrc.name = 'AUX_SRC'
    b.link(auxc.outputs[0], auxsrc.inputs['Color'])
    AO = auxsrc.outputs[0]
    EDGE = auxsrc.outputs[1]

    L = b.lib(r['base'], r.get('scale', 1.0), rot=r.get('rot', 0.0))
    bc = L['bc']
    if r.get('tint'):
        bc = b.mix(bc, tuple(r['tint']), 1.0, 'MULTIPLY')
    if r.get('hue'):  # value/saturation variation
        hv = b.node('ShaderNodeHueSaturation')
        hv.inputs['Saturation'].default_value = r['hue'][0]
        hv.inputs['Value'].default_value = r['hue'][1]
        b.link(bc, hv.inputs['Color'])
        bc = hv.outputs['Color']
    rough = L['rough']
    metal = L['metal']
    nrm = L['n']
    if 'metal' in r:
        metal = b.val(r['metal'])
    if r.get('rough_add') or r.get('rough_mul'):
        rough = b.math('MULTIPLY_ADD', rough, r.get('rough_mul', 1.0)) if False else rough
        rough = b.math('MULTIPLY', rough, r.get('rough_mul', 1.0))
        rough = b.math('ADD', rough, r.get('rough_add', 0.0), clamp=True)

    # big colour breakup (always on, subtle)
    brk = b.noise(r.get('breakup_scale', 1.2), 4, 0.5)
    bc = b.mix(bc, b.mix(bc, (0.5, 0.5, 0.5), 1.0, 'MULTIPLY'), b.math('MULTIPLY', b.ramp(brk, 0.35, 0.75), r.get('breakup', 0.25)), 'MIX')
    bc = b.mix(bc, b.mix(bc, (1.3, 1.3, 1.3), 1.0, 'MULTIPLY'), b.math('MULTIPLY', b.ramp(brk, 0.55, 0.3), r.get('breakup', 0.25) * 0.6), 'MIX')

    chip = None
    if r.get('paint') is not None:
        # chipped paint layer over base: chips where edges + noise
        n1 = b.noise(r.get('chip_scale', 9.0), 8, 0.7, dist=0.3)
        chipf = b.math('ADD', b.math('MULTIPLY', EDGE, r.get('chip', 0.5) * 1.6), b.math('MULTIPLY', n1, 0.9))
        chip = b.ramp(chipf, 0.98 - r.get('chip_global', 0.0), 1.06 - r.get('chip_global', 0.0))
        pc = tuple(float(c) for c in __import__('envlib.tex', fromlist=['x']).srgb_to_lin(r['paint']))  # sRGB in
        pnoise = b.noise(3.0, 4, 0.5)
        paint = b.mix(tuple(pc), tuple(c * 0.86 for c in pc), pnoise)
        if r.get('under'):
            U = b.lib(r['under'], r.get('under_scale', 1.0))
            ubc, urough, umetal, un = U['bc'], U['rough'], U['metal'], U['n']
        else:
            ubc, urough, umetal, un = bc, rough, metal, nrm
        bc = b.mix(paint, ubc, chip)
        prough = r.get('paint_rough', 0.55)
        rough = b.mixf(b.math('ADD', b.math('MULTIPLY', pnoise, 0.15), prough), urough, chip)
        metal = b.mixf(r.get('paint_metal', 0.0), umetal, chip)
        nrm = b.mixv(nrm, un, chip)
    # edge brightening / wear
    if r.get('edge', 0.0) > 0:
        en = b.noise(14.0, 6, 0.6)
        ef = b.math('MULTIPLY', b.ramp(b.math('ADD', EDGE, b.math('MULTIPLY', en, 0.5)), 0.55, 0.95), r['edge'])
        ec = r.get('edge_col')
        target = b.mix(bc, (1.45, 1.45, 1.4), 1.0, 'MULTIPLY') if ec is None else tuple(ec)
        bc = b.mix(bc, target, ef)
        rough = b.mixf(rough, r.get('edge_rough', 0.4), b.math('MULTIPLY', ef, 0.6))
    # cavity dirt
    if r.get('dirt', 0.0) > 0:
        dn = b.noise(5.0, 5, 0.6)
        df = b.math('MULTIPLY', b.ramp(b.math('SUBTRACT', b.math('ADD', b.math('SUBTRACT', 1.0, AO), b.math('MULTIPLY', dn, 0.2)), 0.1), 0.05, 0.7), r['dirt'])
        bc = b.mix(bc, tuple(r.get('dirt_col', (0.12, 0.1, 0.075))), df)
        rough = b.mixf(rough, 0.92, b.math('MULTIPLY', df, 0.7))
    # ground grime (object space height)
    if r.get('ground', 0.0) > 0:
        tc = b.node('ShaderNodeTexCoord')
        sep = b.node('ShaderNodeSeparateXYZ')
        b.link(tc.outputs['Object'], sep.inputs[0])
        gn = b.noise(6.0, 6, 0.65)
        gz = b.math('ADD', sep.outputs['Z'], b.math('MULTIPLY', gn, r['ground'] * 0.7))
        gf = b.math('MULTIPLY', b.ramp(gz, r['ground'] * 1.1, r['ground'] * 0.15), r.get('ground_amt', 0.8))
        bc = b.mix(bc, tuple(r.get('ground_col', (0.2, 0.16, 0.11))), gf)
        rough = b.mixf(rough, 0.95, gf)
        metal = b.mixf(metal, 0.0, gf)
    # vertical streaks (rust / water)
    if r.get('streak', 0.0) > 0:
        sn = b.noise(r.get('streak_scale', 4.0), 8, 0.7, stretch=(14.0, 14.0, 0.6))
        sm = b.noise(1.5, 3, 0.5)
        sf = b.math('MULTIPLY', b.math('MULTIPLY', b.ramp(sn, 0.52, 0.72), b.ramp(sm, 0.4, 0.65)), r['streak'])
        bc = b.mix(bc, tuple(r.get('streak_col', (0.26, 0.11, 0.04))), sf)
        rough = b.mixf(rough, 0.85, b.math('MULTIPLY', sf, 0.5))
    # moss / lichen on up-facing surfaces
    if r.get('moss', 0.0) > 0:
        gn = b.node('ShaderNodeNewGeometry')
        sz = b.node('ShaderNodeSeparateXYZ')
        b.link(gn.outputs['Normal'], sz.inputs[0])
        mn = b.noise(2.5, 8, 0.7)
        mf = b.math('MULTIPLY', b.math('MULTIPLY', b.ramp(sz.outputs['Z'], 0.45, 0.85), b.ramp(mn, 0.45, 0.65)), r['moss'])
        bc = b.mix(bc, tuple(r.get('moss_col', (0.16, 0.2, 0.07))), mf)
        rough = b.mixf(rough, 0.95, mf)
    # procedural bump on top of library normal
    if r.get('bump', 0.0) > 0:
        bn = b.noise(r.get('bump_scale', 30.0), 8, 0.65)
        bump = b.node('ShaderNodeBump')
        bump.inputs['Strength'].default_value = r['bump']
        bump.inputs['Distance'].default_value = r.get('bump_dist', 0.002)
        b.link(bn, bump.inputs['Height'])
        b.link(nrm, bump.inputs['Normal'])
        nrm = bump.outputs['Normal']
    # AO into colour a little (cavity)
    bc = b.mix(bc, b.mix(bc, (0.0, 0.0, 0.0), 1.0, 'MIX'), b.math('MULTIPLY', b.math('SUBTRACT', 1.0, AO), r.get('ao_bc', 0.35)))

    b.link(bc, bsdf.inputs['Base Color'])
    b.link(rough, bsdf.inputs['Roughness'])
    b.link(metal, bsdf.inputs['Metallic'])
    b.link(nrm, bsdf.inputs['Normal'])
    # named sockets for baking
    orm = b.node('ShaderNodeCombineColor')
    orm.name = 'ORM'
    b.link(AO, orm.inputs[0])
    b.link(rough, orm.inputs[1])
    b.link(metal, orm.inputs[2])
    mk = r.get('mask', (0, 0, 0))
    if chip is not None and r.get('mask_paint_only'):
        mask = b.mix((0, 0, 0), tuple(mk), b.math('SUBTRACT', 1.0, chip))
    else:
        mask = b.rgb(mk)
    m['_bc'] = 0
    n_bc = b.node('NodeReroute')
    n_bc.name = 'OUT_BC'
    b.link(bc, n_bc.inputs[0])
    n_m = b.node('NodeReroute')
    n_m.name = 'OUT_M'
    b.link(mask, n_m.inputs[0])
    m['bsdf'] = bsdf.name
    return m


def _target(mat, img):
    nt = mat.node_tree
    t = nt.nodes.get('BAKE_TARGET')
    if t is None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.name = 'BAKE_TARGET'
        uv = nt.nodes.new('ShaderNodeUVMap')
        uv.uv_map = 'UVMap'
        nt.links.new(uv.outputs['UV'], t.inputs['Vector'])
    t.image = img
    for n in nt.nodes:
        n.select = False
    t.select = True
    nt.nodes.active = t


def _route_emit(mat, sock_name):
    nt = mat.node_tree
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    emit = nt.nodes['BAKE_EMIT']
    src = nt.nodes[sock_name].outputs[0]
    nt.links.new(src, emit.inputs['Color'])
    nt.links.new(emit.outputs[0], out.inputs['Surface'])


def _route_bsdf(mat):
    nt = mat.node_tree
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    nt.links.new(nt.nodes[mat['bsdf']].outputs[0], out.inputs['Surface'])


def _img(name, res, noncolor):
    im = bpy.data.images.get(name)
    if im:
        bpy.data.images.remove(im)
    im = bpy.data.images.new(name, res, res, alpha=False, float_buffer=False)
    im.colorspace_settings.name = 'Non-Color' if noncolor else 'sRGB'
    return im


def bake_piece(obj, prefix, res, mask_res=None, want_mask=False):
    """Bake all materials of obj into T_<prefix>_BC/N/ORM(/M).png."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.render.use_simplify = False
    sc.render.bake.margin = max(4, res // 128)
    sc.render.bake.margin_type = 'EXTEND'
    sc.render.bake.use_clear = True
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.data.uv_layers.active = obj.data.uv_layers['UVMap']
    mats = [s.material for s in obj.material_slots]
    out_dir = os.path.dirname(prefix)
    bl.ensure(out_dir)

    def bake(kind, img, **kw):
        for m in mats:
            _target(m, img)
        bpy.ops.object.bake(type=kind, margin=sc.render.bake.margin, use_clear=True, **kw)

    # pass 1: AUX (AO + edge) at half res
    sc.cycles.samples = 1
    aux = _img(os.path.basename(prefix) + '_AUX', max(256, res // 2), True)
    for m in mats:
        nt = m.node_tree
        _route_emit_src(m, nt.nodes['AUX_COMBINE'].outputs[0])
    bake('EMIT', aux)
    _blur_image(aux, max(1.0, aux.size[0] / 512.0))
    # swap AUX source to the baked image
    for m in mats:
        nt = m.node_tree
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = aux
        uv = nt.nodes.new('ShaderNodeUVMap')
        uv.uv_map = 'UVMap'
        nt.links.new(uv.outputs['UV'], t.inputs['Vector'])
        nt.links.new(t.outputs['Color'], nt.nodes['AUX_SRC'].inputs['Color'])
    # pass 2: BC, ORM, (M)
    bc = _img(os.path.basename(prefix) + '_BC', res, False)
    for m in mats:
        _route_emit(m, 'OUT_BC')
    bake('EMIT', bc)
    orm = _img(os.path.basename(prefix) + '_ORM', res, True)
    for m in mats:
        _route_emit(m, 'ORM')
    bake('EMIT', orm)
    imgs = {'BC': bc, 'ORM': orm}
    if want_mask:
        mres = mask_res or max(256, res // 4)
        mk = _img(os.path.basename(prefix) + '_M', mres, True)
        for m in mats:
            _route_emit(m, 'OUT_M')
        sc.render.bake.margin = max(4, mres // 128)
        bake('EMIT', mk)
        imgs['M'] = mk
        sc.render.bake.margin = max(4, res // 128)
    # pass 3: normal
    for m in mats:
        _route_bsdf(m)
    nimg = _img(os.path.basename(prefix) + '_N', res, True)
    bake('NORMAL', nimg, normal_space='TANGENT', normal_r='POS_X', normal_g='NEG_Y', normal_b='POS_Z')
    imgs['N'] = nimg
    for k, im in imgs.items():
        path = prefix + '_' + k + '.png'
        im.filepath_raw = path
        im.file_format = 'PNG'
        sc.render.image_settings.color_depth = '8'
        im.save()
    bpy.data.images.remove(aux)
    return imgs


def _blur_image(img, sigma):
    import numpy as np
    from . import tex
    w, h = img.size
    a = np.zeros(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    a[..., :3] = tex.blur(np.ascontiguousarray(a[..., :3]), sigma)
    img.pixels.foreach_set(a.ravel())
    img.update()


def _route_emit_src(mat, src):
    nt = mat.node_tree
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    emit = nt.nodes['BAKE_EMIT']
    nt.links.new(src, emit.inputs['Color'])
    nt.links.new(emit.outputs[0], out.inputs['Surface'])


def finalize_piece(obj, slot_name, prefix, has_mask=False, tint=None, opacity=False):
    """Collapse all slots into the single baked material slot."""
    me = obj.data
    for p in me.polygons:
        p.material_index = 0
    me.materials.clear()
    m = bl.baked_material(slot_name, prefix, has_mask=has_mask, tint=tint, opacity=opacity)
    me.materials.append(m)
    # drop the helper UV map so the FBX carries only the bake layout
    if 'UVTex' in me.uv_layers:
        me.uv_layers.remove(me.uv_layers['UVTex'])
    return m
