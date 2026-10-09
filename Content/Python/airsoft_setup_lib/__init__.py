"""Andrew's Airsoft editor setup helpers.

Modules:
    common     - logging, paths, JSON asset registry, summary counters (imports `unreal`)
    importers  - FBX / PNG / WAV import with change detection (imports `unreal`)
    materials  - master materials, instances, slot assignment (imports `unreal`)
    lighting   - sky / sun / fog / post / fixture lights (imports `unreal`)
    levels     - builds the five maps from `layouts` (imports `unreal`)
    layouts    - pure data: map layouts, asset sizes and fallbacks (no `unreal`; also used by
                 Tools/Unreal/check_layouts.py outside the editor)

Nothing here imports `unreal` at package import time, so `layouts` can be loaded by plain Python.
"""

VERSION = "1.0.0"
