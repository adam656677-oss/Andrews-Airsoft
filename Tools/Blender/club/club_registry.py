"""Asset registry shared by the club/armory builder modules."""

import os

ASSETS = {}
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")

# Lineup sheet layout (rows back to front).
LINEUPS = {
    "club": [
        ["BoxTruck", "Car_Sedan", "Car_Coupe", "Dumpster", "Kiosk"],
        ["BackBar_4m", "SpeakerStack", "DJBooth", "NeonSign_Velvet", "StreetLamp"],
        ["BarCounter_4m", "BoothSofa_Curved", "Chandelier", "Planter_Concrete", "MovingHeadLight"],
        ["BarStool", "BoothTable", "HighTable", "Armchair_Leather", "VelvetRopePost", "WallSconce", "Bollard", "TrashBags"],
    ],
    "armory": [
        ["WallPanel_Walnut_4m", "ArmorySign"],
        ["GunDisplayBay", "ArmoryCounter", "Mannequin_Torso", "CeilingLight_Brass"],
        ["RugPersian", "GunCase_Hard", "AmmoCrate_Wood", "BankersLamp"],
    ],
}


def asset(aid, group="Club", **kw):
    """Decorator: registers fn(A) as the builder of asset `aid`."""

    def deco(fn):
        ASSETS[aid] = {"fn": fn, "kw": dict(group=group, **kw)}
        return fn

    return deco


def font(name):
    p = os.path.join(FONTS, name)
    return p if os.path.exists(p) else None
