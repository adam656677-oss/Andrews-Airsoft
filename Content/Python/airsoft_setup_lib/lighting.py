"""Lighting and post for every playable map (Lumen GI/reflections, VSM, TSR) tuned for an RTX 2070 at 4K.

Light scale: the game's C++ uses UE-default-scale values (BB tracer emissive ~8, objective glow ~4 cd), so the
maps use the same low physical scale: sun 5-10 lux, local lights a few candela, auto exposure around EV100 0-3.
"""

import unreal

from . import common as C
from . import layouts as L

PRESETS = {
    "ironwood_golden": {
        "sun": {"pitch": -9.0, "yaw": -70.0, "lux": 7.0, "temp": 3300, "angle": 1.2},
        "sky": {"intensity": 1.0, "lower": (0.05, 0.045, 0.04)}, "clouds": True,
        "fog": {"density": 0.03, "falloff": 0.22, "start": 1500.0, "inscatter": (0.42, 0.33, 0.24),
                "vol_scatter": 0.75, "vol_albedo": (235, 214, 192), "vol_extinction": 1.0, "vol_distance": 9000.0},
        "exposure": (-0.5, 3.0, 0.2), "white_temp": 6100.0, "bloom": 0.5, "vignette": 0.3, "grain": 0.12,
        "ca": 0.08, "saturation": 1.03, "contrast": 1.04, "local_exposure": (0.75, 0.9),
    },
    "staging_golden": {
        "sun": {"pitch": -11.0, "yaw": 15.0, "lux": 8.0, "temp": 3600, "angle": 1.0},
        "sky": {"intensity": 1.0, "lower": (0.05, 0.045, 0.04)}, "clouds": True,
        "fog": {"density": 0.025, "falloff": 0.2, "start": 2000.0, "inscatter": (0.4, 0.33, 0.25),
                "vol_scatter": 0.7, "vol_albedo": (235, 220, 200), "vol_extinction": 0.8, "vol_distance": 8000.0},
        "exposure": (-1.5, 3.2, 0.3), "white_temp": 6200.0, "bloom": 0.45, "vignette": 0.3, "grain": 0.1,
        "ca": 0.06, "saturation": 1.02, "contrast": 1.03, "local_exposure": (0.75, 0.9),
    },
    # Velvet Club: rain-soaked neon street. Teal-blue haze (height fog + volumetric fog with a teal albedo so
    # every sign blooms its own colour into the air), cool moon, the neon and sodium practicals do the work.
    # Grade (shared with nightjar_rain; FPostProcessSettings colour wheels, (r, g, b, w)): cool teal shadows,
    # slightly warm highlights, saturated neon; local exposure keeps the signs from clipping.
    "velvet_night": {
        "sun": {"pitch": -38.0, "yaw": 125.0, "lux": 0.2, "temp": 9500, "angle": 0.6},
        "sky": {"intensity": 0.3, "lower": (0.008, 0.012, 0.014)}, "clouds": True,
        "fog": {"density": 0.075, "falloff": 0.3, "start": 200.0, "inscatter": (0.03, 0.065, 0.08),
                "vol_scatter": 0.7, "vol_albedo": (185, 228, 235), "vol_extinction": 2.4, "vol_distance": 6000.0},
        "exposure": (-2.5, 1.0, 0.8), "white_temp": 6300.0, "bloom": 1.0, "vignette": 0.4, "grain": 0.16,
        "ca": 0.1, "saturation": 1.12, "contrast": 1.08, "local_exposure": (0.62, 0.85),
        "grade": {"shadows_gain": (0.9, 1.0, 1.1, 1.0), "shadows_saturation": (1.0, 1.0, 1.0, 1.15),
                  "highlights_gain": (1.04, 1.0, 0.96, 1.0), "midtones_saturation": (1.0, 1.0, 1.0, 1.06)},
    },
    # Nightjar Garage: rainy night, overcast moon, wet haze; sodium + cold fluorescent practicals do the work.
    # Exposure range matches velvet_night so both night maps meter alike.
    "nightjar_rain": {
        "sun": {"pitch": -35.0, "yaw": 200.0, "lux": 0.2, "temp": 9000, "angle": 1.5},
        "sky": {"intensity": 0.3, "lower": (0.012, 0.011, 0.012)}, "clouds": True,
        "fog": {"density": 0.08, "falloff": 0.3, "start": 200.0, "inscatter": (0.04, 0.058, 0.066),
                "vol_scatter": 0.65, "vol_albedo": (205, 200, 212), "vol_extinction": 2.4, "vol_distance": 6000.0},
        "exposure": (-2.5, 1.0, 0.6), "white_temp": 6300.0, "bloom": 0.85, "vignette": 0.35, "grain": 0.18,
        "ca": 0.1, "saturation": 1.04, "contrast": 1.07, "local_exposure": (0.7, 0.85),
        "grade": {"shadows_gain": (0.9, 1.0, 1.1, 1.0), "shadows_saturation": (1.0, 1.0, 1.0, 1.15),
                  "highlights_gain": (1.04, 1.0, 0.96, 1.0), "midtones_saturation": (1.0, 1.0, 1.0, 1.06)},
    },
    # Saltmarsh Terminal: cold teal-blue night in the rain over a container port. Teal haze and moonlight, the
    # sodium high-masts lay orange pools between black container canyons; deep shadows, cool grade.
    "saltmarsh_rain": {
        "sun": {"pitch": -32.0, "yaw": 150.0, "lux": 0.25, "temp": 10000, "angle": 1.2},
        "sky": {"intensity": 0.3, "lower": (0.006, 0.012, 0.016)}, "clouds": True,
        "fog": {"density": 0.08, "falloff": 0.28, "start": 300.0, "inscatter": (0.025, 0.06, 0.075),
                "vol_scatter": 0.7, "vol_albedo": (175, 222, 232), "vol_extinction": 2.2, "vol_distance": 7000.0},
        "exposure": (-2.5, 1.0, 0.7), "white_temp": 6300.0, "bloom": 0.9, "vignette": 0.42, "grain": 0.18,
        "ca": 0.1, "saturation": 1.06, "contrast": 1.1, "local_exposure": (0.66, 0.85),
        "grade": {"shadows_gain": (0.86, 1.0, 1.14, 1.0), "shadows_saturation": (1.0, 1.0, 1.0, 1.2),
                  "highlights_gain": (1.05, 1.0, 0.94, 1.0), "midtones_saturation": (1.0, 1.0, 1.0, 1.04)},
    },
    # Ledger Tower: top floors of a high-rise at night. Cold teal city light through the glass, rain, deep shadow
    # inside; warm practicals (pendants, brass lamps) carry the interior. Interior exposure: brighter range than the
    # street maps so the warm pools read, still dark corners.
    "ledger_night": {
        "sun": {"pitch": -28.0, "yaw": 120.0, "lux": 0.18, "temp": 10500, "angle": 1.2},
        "sky": {"intensity": 0.35, "lower": (0.006, 0.012, 0.016)}, "clouds": True,
        "fog": {"density": 0.05, "falloff": 0.06, "start": 400.0, "inscatter": (0.025, 0.055, 0.07),
                "vol_scatter": 0.6, "vol_albedo": (180, 220, 232), "vol_extinction": 1.6, "vol_distance": 9000.0},
        "exposure": (-2.0, 1.2, 0.8), "white_temp": 6200.0, "bloom": 0.85, "vignette": 0.45, "grain": 0.16,
        "ca": 0.1, "saturation": 1.05, "contrast": 1.12, "local_exposure": (0.66, 0.85),
        "grade": {"shadows_gain": (0.86, 1.0, 1.14, 1.0), "shadows_saturation": (1.0, 1.0, 1.0, 1.2),
                  "highlights_gain": (1.06, 1.0, 0.93, 1.0), "midtones_saturation": (1.0, 1.0, 1.0, 1.04)},
    },
    "menu_armory": {
        "sun": {"pitch": -30.0, "yaw": 40.0, "lux": 0.05, "temp": 6500, "angle": 1.0, "shadows": False},
        "sky": {"intensity": 0.15, "lower": (0.02, 0.015, 0.01)}, "clouds": False,
        "fog": {"density": 0.02, "falloff": 0.2, "start": 0.0, "inscatter": (0.05, 0.04, 0.03),
                "vol_scatter": 0.7, "vol_albedo": (230, 205, 180), "vol_extinction": 1.2, "vol_distance": 3000.0},
        "exposure": (-1.5, 1.0, 0.5), "white_temp": 6000.0, "bloom": 0.6, "vignette": 0.4, "grain": 0.1,
        "ca": 0.06, "saturation": 1.04, "contrast": 1.05, "local_exposure": (0.7, 0.85),
    },
}

# Light fixtures carried by props (Points from the JSON, else layouts.DEFAULT_POINTS)
FIXTURES = {
    "StreetLamp": {"kind": "point", "point": "Light", "color": "Sodium", "cd": 22.0, "radius": 16.0, "src": 12.0,
                   "vol": 1.5, "shadows": False},
    "Chandelier": {"kind": "point", "point": "Light", "color": "Warm", "cd": 9.0, "radius": 11.0, "src": 20.0,
                   "shadows": True},
    "WallSconce": {"kind": "point", "point": "Light", "color": "Warm", "cd": 2.2, "radius": 4.5, "src": 5.0,
                   "shadows": False},
    "CeilingLight_Brass": {"kind": "point", "point": "Light", "color": "Warm", "cd": 6.0, "radius": 9.0, "src": 15.0,
                           "shadows": False},
    "BankersLamp": {"kind": "spot", "point": "Light", "color": "Warm", "cd": 1.5, "radius": 3.0, "cone": (40, 70),
                    "pitch": -70.0, "src": 3.0, "shadows": True},
    "NeonSign_Velvet": {"kind": "rect", "point": "Light", "color": "Magenta", "cd": 16.0, "radius": 12.0, "w": 250.0,
                        "h": 110.0, "shadows": False, "vol": 2.0},
    "FloodlightTower": {"kind": "spot", "point": "Light", "color": (1.0, 0.9, 0.78), "cd": 280.0, "radius": 75.0,
                        "cone": (28, 52), "pitch": -24.0, "shadows": True, "vol": 1.0, "src": 40.0},
    "MovingHeadLight": {"kind": "spot", "point": "Beam", "color": "Magenta", "cd": 45.0, "radius": 30.0, "cone": (5, 12),
                        "pitch": 22.0, "shadows": False, "vol": 6.0},
    "BackBar_4m": {"kind": "rect", "point": "LEDTop", "color": "Amber", "cd": 6.0, "radius": 4.0, "w": 380.0, "h": 12.0,
                   "pitch": -90.0, "shadows": False},
    # Nightjar Garage kit (Tools/Blender/garage). Rect: w across the tube (local Y), h along it (local X after pitch).
    "Garage_LightFluo": {"kind": "rect", "point": "Light", "color": "Cool", "cd": 6.0, "radius": 9.0, "w": 14.0,
                         "h": 140.0, "pitch": -90.0, "shadows": False, "vol": 0.6},
    "Garage_LightSodium": {"kind": "spot", "point": "Light", "color": "Sodium", "cd": 12.0, "radius": 13.0,
                           "cone": (45, 75), "pitch": -40.0, "src": 8.0, "shadows": False, "vol": 1.4},
    "Garage_ExitSign": {"kind": "point", "point": "Light", "color": "Green", "cd": 0.4, "radius": 3.0, "src": 10.0,
                        "shadows": False},
    "Garage_TicketBooth": {"kind": "point", "point": "Light", "color": "Warm", "cd": 1.6, "radius": 5.0, "src": 15.0,
                           "shadows": False},
    # Saltmarsh Terminal kit (Tools/Blender/harbor). High-mast sodium floods: one shadowed spot each (4 on the map);
    # 24 m up, so ~(24/4)^2 the candela of a 4 m street lamp for a similar pool on the ground.
    "Harbor_FloodMast": {"kind": "spot", "point": "Light", "color": "Sodium", "cd": 700.0, "radius": 52.0,
                         "cone": (40, 62), "pitch": -55.0, "src": 40.0, "shadows": True, "vol": 1.2},
    # Ledger Tower kit (Tools/Blender/tower). Linear pendants: soft warm rect under the diffuser, unshadowed (the map
    # places a few shadowed key spots instead). Rect: w along the pendant (local Y), h across it.
    "Tower_PendantLinear": {"kind": "rect", "point": "Light", "color": "Warm", "cd": 7.0, "radius": 7.0, "w": 230.0,
                            "h": 6.0, "pitch": -90.0, "shadows": False, "vol": 0.4},
    "Harbor_Gatehouse": {"kind": "point", "point": "Light", "color": "Warm", "cd": 2.5, "radius": 7.0, "src": 30.0,
                         "shadows": False, "vol": 1.0},
    # Neon street kit (Tools/Blender/club/neon_kit.py). Signs light the wet street in their own colour: unshadowed
    # (cheap; the emissive tubes also feed Lumen), large source radius so the highlight on wet asphalt is a soft
    # smear instead of a pin-prick, high volumetric scattering so each sign glows in the teal haze.
    "Neon_BladeRamen": {"kind": "point", "point": "Light", "color": "Red", "cd": 9.0, "radius": 11.0, "src": 45.0,
                        "shadows": False, "vol": 3.0},
    "Neon_BladeHotel": {"kind": "point", "point": "Light", "color": "Magenta", "cd": 11.0, "radius": 12.0, "src": 55.0,
                        "shadows": False, "vol": 3.0},
    "Neon_BladeGames": {"kind": "point", "point": "Light", "color": "Cyan", "cd": 9.0, "radius": 11.0, "src": 50.0,
                        "shadows": False, "vol": 3.0},
    "Neon_BladeIzakaya": {"kind": "point", "point": "Light", "color": "Pink", "cd": 8.0, "radius": 10.0, "src": 45.0,
                          "shadows": False, "vol": 3.0},
    "Neon_BladeVelvet": {"kind": "point", "point": "Light", "color": "Magenta", "cd": 12.0, "radius": 12.0, "src": 60.0,
                         "shadows": False, "vol": 3.0},
    "Neon_Karaoke": {"kind": "rect", "point": "Light", "color": "Violet", "cd": 8.0, "radius": 11.0, "w": 260.0, "h": 70.0,
                     "pitch": -20.0, "shadows": False, "vol": 2.5},
    "Neon_BoxPawn": {"kind": "rect", "point": "Light", "color": "Green", "cd": 8.0, "radius": 11.0, "w": 240.0, "h": 90.0,
                     "pitch": -20.0, "shadows": False, "vol": 2.5},
    "Neon_PharmacyCross": {"kind": "point", "point": "Light", "color": "Green", "cd": 6.0, "radius": 9.0, "src": 35.0,
                           "shadows": False, "vol": 2.5},
    "Neon_Cocktails": {"kind": "point", "point": "Light", "color": "Pink", "cd": 6.0, "radius": 9.0, "src": 50.0,
                       "shadows": False, "vol": 2.5},
    "Neon_ArrowBar": {"kind": "point", "point": "Light", "color": "Amber", "cd": 5.0, "radius": 8.0, "src": 50.0,
                      "shadows": False, "vol": 2.0},
    "Neon_OpenSign": {"kind": "point", "point": "Light", "color": "Red", "cd": 0.6, "radius": 3.0, "src": 15.0,
                      "shadows": False},
    "Street_Shopfront": {"kind": "rect", "point": "Light", "color": "Warm", "cd": 4.0, "radius": 9.0, "w": 340.0, "h": 200.0,
                         "pitch": -25.0, "shadows": False, "vol": 1.5},
    "Street_Vending": {"kind": "point", "point": "Light", "color": "Cool", "cd": 1.5, "radius": 4.0, "src": 30.0,
                       "shadows": False},
    "Street_FireBarrel": {"kind": "point", "point": "Light", "color": (1.0, 0.42, 0.1), "cd": 6.0, "radius": 8.0,
                          "src": 15.0, "shadows": False, "vol": 2.0},
}
SHADOW_BUDGET = 12

_ENGINE_CLOUD_MAT = "/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst"


def color_of(c):
    if isinstance(c, (tuple, list)):
        return C.lc(c)
    return C.lc(L.EMISSIVE_COLORS.get(c, (1.0, 1.0, 1.0)))


def comp_of(actor, cls):
    try:
        return actor.get_component_by_class(cls)
    except Exception:
        return None


def set_pp(s, name, value):
    ok = C.try_set(s, name, value, quiet=True)
    if ok:
        C.try_set(s, "override_" + name, True, quiet=True)
    else:
        C.SUMMARY.once("pp:" + name, "post-process setting '%s' not available in this engine version" % name)
    return ok


def _movable(comp):
    try:
        comp.set_mobility(unreal.ComponentMobility.MOVABLE)
    except Exception:
        C.try_set(comp, "mobility", unreal.ComponentMobility.MOVABLE, quiet=True)


# ---------------------------------------------------------------------------------------------
def build_environment(preset_name, spawn, interior=False):
    """Sky atmosphere, sun, sky light, clouds, height fog and an infinite post-process volume."""
    p = PRESETS.get(preset_name)
    if not p:
        return
    n = 0
    try:
        spawn(unreal.SkyAtmosphere, C.vec(0, 0, 0), C.rot(), "SkyAtmosphere", "Lighting")
        n += 1
    except Exception as e:
        C.SUMMARY.note("SkyAtmosphere: %s" % e)
    try:
        s = p["sun"]
        sun = spawn(unreal.DirectionalLight, C.vec(0, 0, 3000), C.rot(pitch=s["pitch"], yaw=s["yaw"]), "Sun", "Lighting")
        dl = comp_of(sun, unreal.DirectionalLightComponent)
        _movable(dl)
        dl.set_intensity(float(s["lux"]))
        try:
            dl.set_use_temperature(True)
            dl.set_temperature(float(s["temp"]))
        except Exception:
            C.try_set(dl, "use_temperature", True)
            C.try_set(dl, "temperature", float(s["temp"]))
        try:
            dl.set_atmosphere_sun_light(True)
        except Exception:
            C.try_set(dl, "atmosphere_sun_light", True)
        C.try_set(dl, "atmosphere_sun_light_index", 0, quiet=True)
        C.try_set(dl, "light_source_angle", float(s.get("angle", 0.5)), quiet=True)
        C.try_set(dl, "cast_cloud_shadows", bool(p.get("clouds")), quiet=True)
        C.try_set(dl, "contact_shadow_length", 0.03, quiet=True)
        dl.set_cast_shadows(bool(s.get("shadows", True)))
        n += 1
    except Exception as e:
        C.SUMMARY.note("Sun: %s" % e)
    try:
        sky = spawn(unreal.SkyLight, C.vec(0, 0, 2000), C.rot(), "SkyLight", "Lighting")
        sl = comp_of(sky, unreal.SkyLightComponent)
        _movable(sl)
        C.try_set(sl, "source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
        C.try_set(sl, "real_time_capture", True)
        sl.set_intensity(float(p["sky"]["intensity"]))
        C.try_set(sl, "lower_hemisphere_is_black", False, quiet=True)
        try:
            sl.set_lower_hemisphere_color(C.lc(p["sky"]["lower"]))
        except Exception:
            pass
        n += 1
    except Exception as e:
        C.SUMMARY.note("SkyLight: %s" % e)
    if p.get("clouds"):
        try:
            cl = spawn(unreal.VolumetricCloud, C.vec(0, 0, 0), C.rot(), "VolumetricCloud", "Lighting")
            vc = comp_of(cl, unreal.VolumetricCloudComponent)
            if vc is not None and not C.try_get(vc, "material"):
                m = unreal.EditorAssetLibrary.load_asset(_ENGINE_CLOUD_MAT)
                if m:
                    C.try_set(vc, "material", m)
            n += 1
        except Exception as e:
            C.SUMMARY.note("VolumetricCloud: %s" % e)
    try:
        f = p["fog"]
        fog = spawn(unreal.ExponentialHeightFog, C.vec(0, 0, -100), C.rot(), "HeightFog", "Lighting")
        hf = comp_of(fog, unreal.ExponentialHeightFogComponent)
        for fn, val in (("set_fog_density", f["density"]), ("set_fog_height_falloff", f["falloff"]),
                        ("set_start_distance", f["start"]), ("set_volumetric_fog", True),
                        ("set_volumetric_fog_scattering_distribution", f["vol_scatter"]),
                        ("set_volumetric_fog_extinction_scale", f["vol_extinction"]),
                        ("set_volumetric_fog_distance", f["vol_distance"])):
            try:
                getattr(hf, fn)(val)
            except Exception as e:
                C.SUMMARY.once("fog:" + fn, "height fog %s failed: %s" % (fn, e))
        try:
            hf.set_fog_inscattering_color(C.lc(f["inscatter"]))
        except Exception:
            C.try_set(hf, "fog_inscattering_luminance", C.lc(f["inscatter"]), quiet=True)
        try:
            a = f["vol_albedo"]
            hf.set_volumetric_fog_albedo(unreal.Color(r=a[0], g=a[1], b=a[2], a=255))
        except Exception:
            pass
        n += 1
    except Exception as e:
        C.SUMMARY.note("HeightFog: %s" % e)
    try:
        build_post(p, spawn)
        n += 1
    except Exception as e:
        C.SUMMARY.note("PostProcessVolume: %s" % e)
    C.SUMMARY.inc("environment actors", n)


def build_post(p, spawn):
    ppv = spawn(unreal.PostProcessVolume, C.vec(0, 0, 0), C.rot(), "PostProcess", "Lighting")
    C.try_set(ppv, "unbound", True)
    C.try_set(ppv, "priority", 0.0, quiet=True)
    s = ppv.get_editor_property("settings")
    # Lumen tuned for an RTX 2070 (software tracing, quality 1 = "high", not epic)
    set_pp(s, "dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.LUMEN)
    set_pp(s, "reflection_method", unreal.ReflectionMethod.LUMEN)
    for k, v in (("lumen_scene_lighting_quality", 1.0), ("lumen_scene_detail", 1.0),
                 ("lumen_scene_view_distance", 20000.0), ("lumen_final_gather_quality", 1.0),
                 ("lumen_reflection_quality", 1.0), ("lumen_max_trace_distance", 20000.0),
                 ("lumen_surface_cache_resolution", 1.0), ("lumen_scene_lighting_update_speed", 1.0),
                 ("lumen_final_gather_lighting_update_speed", 1.0)):
        set_pp(s, k, v)
    mn, mx, bias = p["exposure"]
    try:
        set_pp(s, "auto_exposure_method", unreal.AutoExposureMethod.AEM_HISTOGRAM)
    except Exception:
        pass
    set_pp(s, "auto_exposure_min_brightness", float(mn))      # EV100 (ExtendDefaultLuminanceRange=True)
    set_pp(s, "auto_exposure_max_brightness", float(mx))
    set_pp(s, "auto_exposure_bias", float(bias))
    set_pp(s, "auto_exposure_speed_up", 2.0)
    set_pp(s, "auto_exposure_speed_down", 1.2)
    set_pp(s, "auto_exposure_apply_physical_camera_exposure", False)
    set_pp(s, "bloom_intensity", float(p["bloom"]))
    set_pp(s, "bloom_threshold", -1.0)
    set_pp(s, "vignette_intensity", float(p["vignette"]))
    if not set_pp(s, "film_grain_intensity", float(p["grain"])):
        set_pp(s, "grain_intensity", float(p["grain"]))
    set_pp(s, "scene_fringe_intensity", min(0.1, float(p["ca"])))
    set_pp(s, "white_temp", float(p["white_temp"]))
    try:
        sat, con = p["saturation"], p["contrast"]
        set_pp(s, "color_saturation", unreal.Vector4(x=1.0, y=1.0, z=1.0, w=float(sat)))
        set_pp(s, "color_contrast", unreal.Vector4(x=1.0, y=1.0, z=1.0, w=float(con)))
    except Exception:
        pass
    for key, prop in (("shadows_gain", "color_gain_shadows"), ("shadows_saturation", "color_saturation_shadows"),
                      ("highlights_gain", "color_gain_highlights"), ("midtones_saturation", "color_saturation_midtones"),
                      ("shadows_offset", "color_offset_shadows")):
        v = (p.get("grade") or {}).get(key)
        if v:
            set_pp(s, prop, unreal.Vector4(x=float(v[0]), y=float(v[1]), z=float(v[2]), w=float(v[3])))
    hi, sh = p["local_exposure"]
    set_pp(s, "local_exposure_highlight_contrast_scale", float(hi))
    set_pp(s, "local_exposure_shadow_contrast_scale", float(sh))
    set_pp(s, "motion_blur_amount", 0.0)
    ppv.set_editor_property("settings", s)
    return ppv


# ---------------------------------------------------------------------------------------------
def spawn_light(spawn, kind, loc, rotation, color="Warm", cd=5.0, radius=10.0, shadows=False, cone=None, w=None,
                h=None, vol=1.0, src=None, label="Light"):
    cls = {"point": unreal.PointLight, "spot": unreal.SpotLight, "rect": unreal.RectLight}[kind]
    ccls = {"point": unreal.PointLightComponent, "spot": unreal.SpotLightComponent,
            "rect": unreal.RectLightComponent}[kind]
    a = spawn(cls, loc, rotation, label, "Lighting/Local")
    c = comp_of(a, ccls)
    _movable(c)
    C.try_set(c, "intensity_units", unreal.LightUnits.CANDELAS, quiet=True)
    c.set_intensity(float(cd))
    c.set_light_color(color_of(color))
    c.set_attenuation_radius(float(radius) * 100.0)
    c.set_cast_shadows(bool(shadows))
    try:
        c.set_volumetric_scattering_intensity(float(vol))
    except Exception:
        pass
    if kind in ("point", "spot") and src:
        try:
            c.set_source_radius(float(src))
        except Exception:
            pass
    if kind == "spot" and cone:
        c.set_inner_cone_angle(float(cone[0]))
        c.set_outer_cone_angle(float(cone[1]))
    if kind == "rect":
        try:
            c.set_source_width(float(w or 100.0))
            c.set_source_height(float(h or 50.0))
            c.set_barn_door_angle(70.0)
        except Exception:
            C.try_set(c, "source_width", float(w or 100.0))
            C.try_set(c, "source_height", float(h or 50.0))
    C.SUMMARY.inc("lights")
    return a, bool(shadows)


def spawn_item_light(spawn, it):
    x, y, z = it["p"]
    return spawn_light(spawn, it["kind"], C.vec(x * 100, y * 100, z * 100),
                       C.rot(pitch=it.get("pitch", 0.0), yaw=it.get("yaw", 0.0)), color=it.get("color", "Warm"),
                       cd=it.get("cd", 5.0), radius=it.get("radius", 10.0), shadows=it.get("shadows", False),
                       cone=it.get("cone"), w=(it.get("w") or 1.0) * 100.0, h=(it.get("h") or 0.5) * 100.0,
                       vol=it.get("vol", 1.0), src=it.get("src"), label="Light_" + it["kind"])


def spawn_fixture(spawn, aid, it, json_assets, world_of_local):
    """Light for a prop with a fixture (StreetLamp, Chandelier, ...). world_of_local(cm local) -> unreal.Vector."""
    fx = dict(FIXTURES.get(aid, {}))
    if not fx:
        return None, False
    over = it.get("light")
    if isinstance(over, dict):
        fx.update(over)
    fx["cd"] = fx.get("cd", 5.0) * fx.pop("cd_scale", 1.0)        # layouts.trim_lights merges neighbours into one
    fx["w"] = fx.get("w", 100.0) * fx.pop("w_scale", 1.0)
    pt = L.asset_point(aid, fx.get("point", "Light"), json_assets)
    if pt is None:
        mn, mx = L.asset_bounds(aid, json_assets)
        pt = ((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, mx[2] * 0.85)
    sc = it.get("scale", (1.0, 1.0, 1.0))
    if isinstance(sc, (int, float)):
        sc = (sc, sc, sc)
    loc = world_of_local(pt)
    yaw = it.get("yaw", 0.0) + fx.get("yaw_off", 0.0)
    return spawn_light(spawn, fx["kind"], loc, C.rot(pitch=fx.get("pitch", 0.0), yaw=yaw), color=fx.get("color"),
                       cd=fx.get("cd", 5.0), radius=fx.get("radius", 10.0), shadows=fx.get("shadows", False),
                       cone=fx.get("cone"), w=fx.get("w", 100.0) * sc[1], h=fx.get("h", 50.0) * sc[2],
                       vol=fx.get("vol", 1.0), src=fx.get("src"), label="Light_" + aid)
