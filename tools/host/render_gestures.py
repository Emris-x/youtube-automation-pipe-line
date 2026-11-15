"""
Renders the host character's gesture library: one short transparent clip per
gesture (idle, talking, pointing, shocked, ...), from a rigged 3D model.

This is a ONE-TIME job per character, not part of a video build. Rendering
3D on a CPU costs a couple of seconds per frame, far too slow to animate a
whole video fresh each time -- so the gestures are rendered once, saved as
small clips in assets/host/<name>/, and src/host_overlay.py lays the right
clip over each part of a finished video.

Every clip starts and ends in the same neutral standing pose and has the
same length, so any clip can follow any other with no visible jump.

Needs Blender's Python module and ffmpeg:
    pip install bpy
    python tools/host/render_gestures.py <model.glb> assets/host/<name>

The model must be a humanoid with a Mixamo-style skeleton (bones named
"mixamorig:Hips", "mixamorig:LeftArm", ...).
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

import bpy
from mathutils import Euler, Vector

FPS = 24
FRAMES = 48           # 2.0 s per clip
WIDTH, HEIGHT = 600, 800
SAMPLES = 20

# Rotations are (x, y, z) degrees on each bone, relative to the model's rest
# pose. Found by test renders for this rig: Arm x raises/lowers the arm,
# ForeArm x bends the elbow, Head x nods, Head y turns, Head z tilts.
NEUTRAL = {"RightArm": (-32, 0, 0), "LeftArm": (-32, 0, 0), "RightForeArm": (12, 0, 0), "LeftForeArm": (12, 0, 0)}


def P(**over):
    p = dict(NEUTRAL)
    p.update(over)
    return p


# name -> list of (frame, pose). Poses between keys are eased. Frame 0 and
# the last frame are always NEUTRAL (added automatically).
GESTURES = {
    "idle": [(12, P(Spine1=(1.5, 0, 0), Head=(0, 3, 0))), (24, P()), (36, P(Spine1=(1.5, 0, 0), Head=(0, -3, 0)))],
    "talk_a": [
        (9, P(LeftArm=(-22, 0, 0), LeftForeArm=(95, 0, 0), Head=(5, 8, 0))),
        (18, P(LeftArm=(-24, 0, 0), LeftForeArm=(76, 0, 0), Head=(-2, 5, 0))),
        (27, P(LeftArm=(-22, 0, 0), LeftForeArm=(98, 0, 0), Head=(5, 9, 0))),
        (37, P(LeftArm=(-24, 0, 0), LeftForeArm=(80, 0, 0), Head=(0, 4, 0))),
    ],
    "talk_b": [
        (9, P(RightArm=(-20, 0, 0), LeftArm=(-20, 0, 0), RightForeArm=(70, 0, 0), LeftForeArm=(70, 0, 0), Head=(4, -6, 0))),
        (19, P(RightArm=(-24, 0, 0), LeftArm=(-24, 0, 0), RightForeArm=(52, 0, 0), LeftForeArm=(52, 0, 0), Head=(-2, -2, 0))),
        (29, P(RightArm=(-20, 0, 0), LeftArm=(-20, 0, 0), RightForeArm=(74, 0, 0), LeftForeArm=(74, 0, 0), Head=(4, 5, 0))),
        (38, P(RightArm=(-26, 0, 0), LeftArm=(-26, 0, 0), RightForeArm=(40, 0, 0), LeftForeArm=(40, 0, 0), Head=(0, 2, 0))),
    ],
    "talk_c": [
        (8, P(RightForeArm=(48, 0, 0), Head=(6, -7, 0), Spine1=(2, 0, 0))),
        (17, P(RightForeArm=(34, 0, 0), Head=(-3, -3, 0))),
        (26, P(RightForeArm=(52, 0, 0), Head=(6, 6, 0), Spine1=(2, 0, 0))),
        (36, P(RightForeArm=(30, 0, 0), Head=(-2, 2, 0))),
    ],
    "point": [
        (9, P(LeftArm=(70, 0, 0), LeftForeArm=(0, 0, 0), Head=(-4, 26, 0), Spine1=(0, 8, 0))),
        (16, P(LeftArm=(62, 0, 0), LeftForeArm=(14, 0, 0), Head=(-4, 24, 0), Spine1=(0, 8, 0))),
        (22, P(LeftArm=(72, 0, 0), LeftForeArm=(0, 0, 0), Head=(-4, 27, 0), Spine1=(0, 8, 0))),
        (36, P(LeftArm=(70, 0, 0), LeftForeArm=(2, 0, 0), Head=(-4, 26, 0), Spine1=(0, 8, 0))),
    ],
    "shock": [
        (7, P(RightArm=(62, 0, 0), LeftArm=(62, 0, 0), RightForeArm=(130, 0, 0), LeftForeArm=(130, 0, 0), Head=(-10, 0, 0), Spine1=(-8, 0, 0))),
        (14, P(RightArm=(60, 0, 0), LeftArm=(60, 0, 0), RightForeArm=(126, 0, 0), LeftForeArm=(126, 0, 0), Head=(-8, 6, 0), Spine1=(-7, 0, 0))),
        (22, P(RightArm=(62, 0, 0), LeftArm=(62, 0, 0), RightForeArm=(130, 0, 0), LeftForeArm=(130, 0, 0), Head=(-10, -6, 0), Spine1=(-8, 0, 0))),
        (36, P(RightArm=(62, 0, 0), LeftArm=(62, 0, 0), RightForeArm=(128, 0, 0), LeftForeArm=(128, 0, 0), Head=(-9, 0, 0), Spine1=(-8, 0, 0))),
    ],
    "think": [
        (10, P(RightArm=(-12, 0, 38), RightForeArm=(125, 0, 0), Head=(8, 0, 12))),
        (24, P(RightArm=(-12, 0, 38), RightForeArm=(120, 0, 0), Head=(10, -4, 14))),
        (37, P(RightArm=(-12, 0, 38), RightForeArm=(125, 0, 0), Head=(8, 0, 12))),
    ],
    "shrug": [
        (9, P(RightShoulder=(24, 0, 0), LeftShoulder=(24, 0, 0), RightArm=(-24, 0, 0), LeftArm=(-24, 0, 0), RightForeArm=(56, 0, 0), LeftForeArm=(56, 0, 0), Head=(0, 0, 12))),
        (30, P(RightShoulder=(22, 0, 0), LeftShoulder=(22, 0, 0), RightArm=(-24, 0, 0), LeftArm=(-24, 0, 0), RightForeArm=(54, 0, 0), LeftForeArm=(54, 0, 0), Head=(0, 0, 12))),
    ],
    "cheer": [
        (8, P(RightArm=(115, 0, 0), RightForeArm=(35, 0, 0), Head=(-8, 0, 0))),
        (15, P(RightArm=(98, 0, 0), RightForeArm=(70, 0, 0), Head=(-4, 0, 0))),
        (22, P(RightArm=(118, 0, 0), RightForeArm=(30, 0, 0), Head=(-8, 0, 0))),
        (29, P(RightArm=(98, 0, 0), RightForeArm=(70, 0, 0), Head=(-4, 0, 0))),
        (36, P(RightArm=(115, 0, 0), RightForeArm=(35, 0, 0), Head=(-8, 0, 0))),
    ],
    "nope": [
        (8, P(Head=(4, -26, 0))),
        (17, P(Head=(4, 26, 0))),
        (26, P(Head=(4, -22, 0))),
        (35, P(Head=(4, 18, 0))),
    ],
    "wave": [
        (9, P(RightArm=(-20, 0, 0), RightForeArm=(140, 0, 0), Head=(4, -8, 6))),
        (15, P(RightArm=(-8, 0, 0), RightForeArm=(132, 0, 0), Head=(4, -8, 6))),
        (21, P(RightArm=(-26, 0, 0), RightForeArm=(142, 0, 0), Head=(4, -8, 6))),
        (27, P(RightArm=(-8, 0, 0), RightForeArm=(132, 0, 0), Head=(4, -8, 6))),
        (35, P(RightArm=(-20, 0, 0), RightForeArm=(140, 0, 0), Head=(4, -8, 6))),
    ],
}


def _ease(t):
    return t * t * (3 - 2 * t)


def pose_at(keys, frame):
    keys = [(0, NEUTRAL)] + list(keys) + [(FRAMES - 1, NEUTRAL)]
    for (f0, p0), (f1, p1) in zip(keys, keys[1:]):
        if f0 <= frame <= f1:
            t = _ease((frame - f0) / max(1, f1 - f0))
            out = {}
            for bone in set(p0) | set(p1):
                a, b = p0.get(bone, (0, 0, 0)), p1.get(bone, (0, 0, 0))
                out[bone] = tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
            return out
    return dict(NEUTRAL)


def setup_scene(glb):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    sc = bpy.context.scene
    arm = next(o for o in sc.objects if o.type == "ARMATURE")
    if arm.animation_data:
        arm.animation_data_clear()  # drop any baked clip that came with the model
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)

    # Framed for a ~1.6 m figure with room for an arm raised overhead.
    centre = Vector((0, 0, 0.93))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 60
    cam.location = centre + Vector((0.7, -3.55, 0.2))
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    for name, loc, energy in (("key", (2.5, -3, 4), 900), ("fill", (-3, -2, 2), 380), ("rim", (0, 3, 3), 600)):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
        light.data.energy = energy
        light.data.size = 3
        light.location = centre + Vector(loc)
        light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()
        sc.collection.objects.link(light)

    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = False
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y = WIDTH, HEIGHT
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    return sc, arm


def main():
    glb, out_dir = sys.argv[-2], sys.argv[-1]
    only = [g for g in os.environ.get("HOST_GESTURES", "").split(",") if g]
    os.makedirs(out_dir, exist_ok=True)
    sc, arm = setup_scene(glb)
    work = tempfile.mkdtemp(prefix="host_frames_")
    done = []
    for name, keys in GESTURES.items():
        if only and name not in only:
            continue
        frame_dir = os.path.join(work, name)
        os.makedirs(frame_dir)
        for f in range(FRAMES):
            for pb in arm.pose.bones:
                pb.rotation_euler = (0, 0, 0)
            for bone, (x, y, z) in pose_at(keys, f).items():
                arm.pose.bones["mixamorig:" + bone].rotation_euler = Euler((math.radians(x), math.radians(y), math.radians(z)))
            sc.render.filepath = os.path.join(frame_dir, f"{f:03d}.png")
            bpy.ops.render.render(write_still=True)
        # VP9 with an alpha channel: a few hundred KB per clip, and ffmpeg can
        # lay it straight over a video.
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", os.path.join(frame_dir, "%03d.png"),
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30", "-auto-alt-ref", "0",
            os.path.join(out_dir, f"{name}.webm"),
        ], check=True)
        if name == "idle":
            shutil.copyfile(os.path.join(frame_dir, "000.png"), os.path.join(out_dir, "poster.png"))
        done.append(name)
        print(f"[host] rendered {name}", flush=True)

    manifest_path = os.path.join(out_dir, "manifest.json")
    gestures = sorted(set(done) | set(json.load(open(manifest_path)).get("gestures", [])) if os.path.exists(manifest_path) else done)
    with open(manifest_path, "w") as f:
        json.dump({"fps": FPS, "frames": FRAMES, "width": WIDTH, "height": HEIGHT, "gestures": gestures}, f, indent=2)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
