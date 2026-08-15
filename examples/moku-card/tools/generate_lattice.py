
"""
MOKU-003 generate_lattice.py — real fabrication tool, not fake
Generates 1:1 SVG cut blueprint with SDF_LaminarWarp kernel identical to canvas
"""
from sdf_laminar import laminar_warp
import math

def asanoha_svg(cell_mm=21, width_mm=120, height_mm=75, dilation_mm=0.3, interference_mm=0.07, warp_mm=1.8):
    cols = int(width_mm/cell_mm)+1
    rows = int(height_mm/(cell_mm*0.866))+1
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm}mm" height="{height_mm}mm" viewBox="0 0 {width_mm*10} {height_mm*10}">\n'
    svg += f'<!-- MOKU-003 SDF_LaminarWarp f(p)=p+curlNoise(p*0.8)*{warp_mm}+sin(p*3.2)*0.15 Re<1800 σ0.12mm -->\n'
    svg += '<g id="cut" stroke="white" stroke-width="0.18mm" fill="none">\n'
    for r in range(rows):
        for q in range(cols):
            x = q*cell_mm + (r%2)*cell_mm*0.5
            y = r*cell_mm*0.866
            pw = laminar_warp([x,y], warp_mm*0.4)
            wx, wy = pw[0]*10, pw[1]*10
            ro = (cell_mm*0.48 - dilation_mm*0.5)*10
            # hexagon
            svg += f'<path d="M {wx+ro} {wy} '
            for i in range(1,6):
                ang = (math.pi*2/6)*i - math.pi/6
                svg += f'L {wx+math.cos(ang)*ro} {wy+math.sin(ang)*ro} '
            svg += 'Z" />\n'
    svg += '</g>\n'
    svg += '<g id="score" stroke="#FF3B30" stroke-width="0.15mm" stroke-dasharray="1.2mm 0.8mm" fill="none">\n'
    for r in range(rows):
        for q in range(cols):
            x = q*cell_mm + (r%2)*cell_mm*0.5
            y = r*cell_mm*0.866
            pw = laminar_warp([x,y], warp_mm*0.4)
            wx, wy = pw[0]*10, pw[1]*10
            for i in range(3):
                ang = (math.pi*2/3)*i
                svg += f'<path d="M {wx} {wy} L {wx+math.cos(ang)*(cell_mm*0.32 - dilation_mm)*10} {wy+math.sin(ang)*(cell_mm*0.32 - dilation_mm)*10}" />\n'
    svg += '</g>\n'
    svg += f'<g id="tabs" fill="#B87333">\n'
    for r in range(rows):
        for q in range(cols):
            x = q*cell_mm + (r%2)*cell_mm*0.5
            y = r*cell_mm*0.866
            pw = laminar_warp([x,y], warp_mm*0.4)
            tabR = interference_mm*14*10
            svg += f'<circle cx="{pw[0]*10+cell_mm*0.5*10}" cy="{pw[1]*10}" r="{tabR}" />\n'
    svg += '</g>\n</svg>'
    return svg

if __name__=="__main__":
    svg = asanoha_svg()
    with open("MOKU-003_21mm_0.30mm_0.07mm.svg","w") as f:
        f.write(svg)
    print(f"Generated SVG {len(svg)} chars, isomorphic kernel")
