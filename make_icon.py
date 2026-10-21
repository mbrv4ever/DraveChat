# -*- coding: utf-8 -*-
"""Icoon voor DraveChat uit het Dravenlock-draaklogo (assets/logo.png)."""
import os
from PIL import Image

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
os.makedirs(ASSETS, exist_ok=True)
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

src = None
for n in ("logo.png", "logo_t.png"):
    p = os.path.join(ASSETS, n)
    if os.path.exists(p):
        src = p
        break

if src:
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    im = im.resize((256, 256), Image.LANCZOS)
    im.save(os.path.join(ASSETS, "icon-256.png"))
    im.resize((64, 64), Image.LANCZOS).save(os.path.join(ASSETS, "icon-64.png"))
    im.save(os.path.join(ASSETS, "icon.ico"), format="ICO", sizes=SIZES)
    print("icon done")
else:
    print("geen logo gevonden in assets/")
