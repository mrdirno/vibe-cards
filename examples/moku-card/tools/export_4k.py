
"""
MOKU-003 export_4k.py — 4K displacement map generator (Pillow)
Real tool: uses same laminar_warp kernel
"""
try:
    from PIL import Image
except ImportError:
    Image=None

from sdf_laminar import laminar_warp, noise2
import math

def export_4k(width=3840, height=2160, warp_mm=1.8, out="MOKU-003_4K_disp.png"):
    if Image is None:
        print("Pillow not available, cannot export PNG")
        return
    im = Image.new("RGB", (width, height))
    px = im.load()
    for y in range(height):
        for x in range(width):
            p = [(x/width)*120, (y/height)*75]
            pw = laminar_warp(p, warp_mm)
            layer_f = pw[1]*0.6 + pw[0]*0.12
            layer = int(abs(layer_f*1.5) % 17)
            h = int((layer/17)*255)
            var = noise2([pw[0]*0.4, pw[1]*0.4])*40
            r = int(max(0,min(255,h+var)))
            g = int(max(0,min(255,h*0.6+var*0.5)))
            b = int(max(0,min(255,h*0.3+var*0.3)))
            px[x,y]=(r,g,b)
        if y%200==0:
            print(f"{y}/{height}")
    im.save(out)
    print(f"Saved {out} {width}x{height}")

if __name__=="__main__":
    export_4k()
