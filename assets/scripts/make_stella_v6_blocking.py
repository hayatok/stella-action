# Stella v6 BLOCKING PASS - rough volumes only, no detail, no textures.
# Ortho front + side renders (Workbench, flat) for silhouette overlay
# against art/stella-model-sheet.png before detail work is trusted.
import bpy, math, os
from mathutils import Vector

ROOT = os.path.expanduser("~/workspace/stella-action")
D = math.radians
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

def mat(name, color):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
    return m

SKIN = mat("skin", (0.98, 0.78, 0.62))
HAIR = mat("hair", (0.0, 0.42, 0.40))
CREAM = mat("cream", (0.95, 0.91, 0.82))
TEAL = mat("teal", (0.0, 0.38, 0.36))
DARK = mat("dark", (0.10, 0.11, 0.14))
SOCK = mat("sock", (0.12, 0.13, 0.18))

def box(name, loc, size, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object
    o.name = name
    o.dimensions = size
    o.rotation_euler = rot
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    return o

def sph(name, loc, scale, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=1.0, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    o.data.materials.append(material)
    return o

def cyl(name, loc, r_top, r_bot, depth, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=r_bot, radius2=r_top,
                                    depth=depth, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.rotation_euler = rot
    o.data.materials.append(material)
    return o

def ribbon(name, rings, material, radial=10):
    verts, faces = [], []
    n = len(rings)
    for (c, rx, ry) in rings:
        for k in range(radial + 1):
            a = math.pi / 2 + 2 * math.pi * k / radial
            verts.append((c.x + rx * math.cos(a), c.y + ry * math.sin(a), c.z))
    st = radial + 1
    for i in range(n - 1):
        for k in range(radial):
            faces.append((i * st + k, (i + 1) * st + k, (i + 1) * st + k + 1, i * st + k + 1))
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(material)
    return o

# ---- body blocks (same layout numbers as the detail build)
sph("Head", (0, -0.004, 1.445), (0.104, 0.092, 0.106), SKIN)
sph("HairCap", (0, 0.012, 1.458), (0.111, 0.099, 0.113), HAIR)
sph("HairBack", (0, 0.045, 1.405), (0.107, 0.088, 0.135), HAIR)
box("Midriff", (0, 0, 1.075), (0.20, 0.148, 0.13), SKIN)
box("Jacket", (0, 0, 1.225), (0.29, 0.19, 0.24), CREAM)
box("Collar", (0, 0.03, 1.375), (0.20, 0.12, 0.12), TEAL)
box("Shorts", (0, 0, 0.89), (0.27, 0.19, 0.22), DARK)
box("Satchel", (-0.205, 0.022, 0.89), (0.085, 0.185, 0.205), DARK)
for s in (+1, -1):
    # arms: puffy sleeve + forearm + hand
    sph(f"Sleeve{s}", (0.158 * s, 0, 1.255), (0.072, 0.068, 0.082), CREAM)
    cyl(f"Forearm{s}", (0.161 * s, 0, 1.00), 0.030, 0.034, 0.20, SKIN)
    sph(f"Hand{s}", (0.161 * s, -0.003, 0.868), (0.042, 0.039, 0.056), DARK)
    # legs: thigh + sock shin + boot
    cyl(f"Thigh{s}", (0.085 * s, 0, 0.74), 0.046, 0.062, 0.46, SKIN)
    cyl(f"Shin{s}", (0.085 * s, 0, 0.37), 0.039, 0.046, 0.28, SOCK)
    box(f"Boot{s}", (0.085 * s, -0.010, 0.115), (0.122, 0.185, 0.20), DARK)
    box(f"BootCuff{s}", (0.085 * s, 0, 0.244), (0.128, 0.142, 0.07), TEAL)
    # twintail: one wide ribbon per side (detail build path, main strand)
    base = [(0.005, 0.005, 0.030, 0.046, 0.020), (0.060, 0.012, -0.060, 0.066, 0.024),
            (0.115, 0.018, -0.180, 0.080, 0.026), (0.155, 0.020, -0.320, 0.086, 0.026),
            (0.170, 0.018, -0.460, 0.080, 0.024), (0.155, 0.014, -0.580, 0.066, 0.021),
            (0.120, 0.010, -0.680, 0.046, 0.017), (0.085, 0.006, -0.755, 0.022, 0.012),
            (0.065, 0.004, -0.790, 0.003, 0.004)]
    rings = [(Vector((0.082 * s + px * s, 0.028 + py, 1.488 + pz)), rx, ry)
             for (px, py, pz, rx, ry) in base]
    ribbon(f"Tail{s}", rings, HAIR)

# ---- ortho renders (Cycles low-sample: Workbench/EEVEE need EGL, absent headless)
scene.render.engine = 'CYCLES'
scene.cycles.samples = 8
scene.cycles.device = 'CPU'
ld = bpy.data.lights.new("Sun", 'SUN')
ld.energy = 3.0
lo = bpy.data.objects.new("Sun", ld)
bpy.context.collection.objects.link(lo)
lo.rotation_euler = (D(50), D(10), D(20))
scene.render.resolution_x = 700
scene.render.resolution_y = 875
scene.render.film_transparent = False
world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.92, 1)
scene.world = world

cam_data = bpy.data.cameras.new("Cam")
cam_data.type = 'ORTHO'
cam_data.ortho_scale = 1.85
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam

def shot(loc, target, out):
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(ROOT, "assets", out)
    bpy.ops.render.render(write_still=True)
    print("BLOCK RENDERED", out)

shot((0, -3, 0.85), (0, 0, 0.85), "blocking_front.png")
shot((3, 0, 0.85), (0, 0, 0.85), "blocking_side.png")   # her left side, face reads screen-right
shot((0, 3, 0.85), (0, 0, 0.85), "blocking_back.png")
print("BLOCKING DONE")
