# Andrew's Airsoft — 4K art (SourceAssets)

This branch holds only the generated 4K source art for the Unreal Engine version (code lives on the `unreal` branch). It is kept separate so code clones stay small.

Get it into your project (run from the root of your `unreal` checkout):

```
git fetch origin art
git checkout FETCH_HEAD -- SourceAssets
git reset -q SourceAssets   # keep it untracked on the code branch (it is git-ignored there)
```

Then open the project in Unreal Engine 5.8 and run `py airsoft_setup.py` (see the README on the `unreal` branch).

Contents (FBX + baked PNG textures, layout per `Tools/Blender/CONVENTIONS.md`): 31 tileable materials, 15 architecture modules, 57 props, 15 guns (incl. BB grenade), 13 attachments, first-person gloves. Regenerate with the Blender scripts in `Tools/Blender/` on the `unreal` branch.
