# Taxi Time - the secret "Kiwi mode" flyer: Kiwi the Senegal parrot (pixel art, v3b style). Plain Python 3, no libraries.
# Every pixel comes from shapes typed into this file; no outside or Blizzard art.
# Reuses the drawing engine of make_flyers_v3b.py (same 96x96 native frame, shading, outline and layout).
#
#   flyer_kiwi.tga = 512x128, 32-bit with alpha, uncompressed, 4 frames of 128x128,
#   frame i at tex coords (i*0.25, (i+1)*0.25, 0, 1): wings up, going down, down, going up.
#   Shown on the bar like the other flyers (SHEET_SIZE 64, SHEET_Y -13).
#
# Usage: python -B make_kiwi.py   -> out\flyer_kiwi.tga (+ .png). Copy the .tga to TaxiTime\media\ by hand.
# (-B so no __pycache__ is left next to the scripts.)
import os

from make_flyers_v3b import (Frame, Pic, ell, pmask, strk, star, feather_wing, FEATHER_ANG, BOB, R5, CELL, PADC, FR,
                             blit, write_png, write_tga)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')


def kiwi(f, R):
    F = Frame(); b = BOB[f]; th, sp = FEATHER_ANG[f]
    P = lambda pts: [(x, y + b) for x, y in pts]
    E = lambda cx, cy, rx, ry, rot=0: ell(cx, cy + b, rx, ry, rot)
    S = lambda cx, cy, rx, ry: (cx, cy + b, rx, ry)
    ws = 0.88                                         # wing size
    sx, sy = 31, 30 + b
    feather_wing(F, sx + 2.5, sy - 1.5, th - 12, sp * 0.9, R, False, ws)
    # short squared green tail, darker tip
    gt = F.add(pmask(P([(21, 33.4), (9.5, 32), (6.4, 32.8), (5.8, 38.6), (8.4, 40.2), (21, 38.6)])), R['tail'],
               sph=S(13, 36, 9, 3.5), line=True)
    F.add(pmask(P([(9.4, 32.1), (6.4, 32.8), (5.8, 38.6), (8.4, 40.2), (9.6, 36.2)])), R['tailtip'], base=2, group=gt, rim=0)
    F.add(strk(P([(20, 36), (9, 36.4)]), [0.8, 0.8]), R['tail'], base=0, flat=True, thr=6, group=gt)
    # far foot (tucked, grey)
    F.add(strk(P([(30, 41), (27, 44), (24, 44.6)]), [2.2, 1.6, 1.2]), R['footfar'], base=2, rim=0)
    # body: green back, yellow-orange belly (the Senegal "V")
    g = F.add(E(30, 35.5, 12, 7.4, -8), R['green'], sph=S(30, 35.5, 12, 7.4), dith=0.5)
    F.add(pmask(P([(22, 39), (31, 34.5), (39, 32.5), (40.5, 37.5), (35, 42), (25, 42.6)])), R['belly'],
          sph=S(33, 36, 9, 7), k=1.2, group=g, rim=0)
    # near foot: grey toes tucked under
    fx, fy = 28, 45.5
    F.add(strk(P([(fx + 4, fy - 4), (fx + 1, fy - 1), (fx - 2, fy)]), [2.6, 2.0, 1.6]), R['foot'], base=2, line=True)
    for dy in (-0.8, 0.9):
        F.add(strk(P([(fx - 1.5, fy + dy * 0.5), (fx - 4, fy + dy)]), [1.2, 1.0]), R['foot'], base=1, thr=5)
    # green chest bib between belly and grey head
    F.add(star(39.5, 31.5 + b, 6.4, 5.2, 9, 10, 1.0), R['green'], sph=S(39.5, 31.5, 6.4, 6.4), line=True)
    # grey head
    hx, hy, hr = 46.5, 26.5, 6.4
    gh = F.add(E(hx, hy, hr, hr * 0.94), R['grey'], sph=S(hx, hy, hr, hr), line=True)
    F.add(E(hx - 2, hy + 4.2, hr * 0.7, 2.2, -10), R['grey'], base=2, group=gh, rim=0, sph=S(hx, hy, hr, hr))
    # dark hooked beak (upper mandible + small lower one)
    bx = hx + hr - 1.6
    F.add(pmask(P([(bx, 23.8), (bx + 3.4, 23.4), (bx + 6.2, 25.8), (bx + 6.4, 30.4), (bx + 5, 29.6), (bx + 3.8, 28),
                   (bx, 29.4)])), R['beak'], sph=S(bx + 2, 24, 5, 4), k=1.2, line=True)
    F.add(pmask(P([(bx + 0.4, 29), (bx + 3.8, 28.2), (bx + 4.2, 30.4), (bx + 1, 31)])), R['beak'], base=1, rim=0)
    # yellow eye with black pupil
    ex, ey = hx + hr * 0.42, hy - 0.8
    F.add(E(ex, ey, 1.8, 1.8), R['iris'], base=2, flat=True, thr=5)
    F.add(E(ex + 0.2, ey, 0.85, 0.9), R['pupil'], base=2, flat=True, thr=4)
    feather_wing(F, sx, sy, th, sp, R, True, ws)
    return F.render()


# real Senegal parrot colours (our own picks)
KIWI = dict(
    far=R5((44, 104, 56)), prim=R5((40, 96, 104)), cov=R5((78, 156, 64)), marg=R5((150, 204, 92)),
    tail=R5((70, 132, 60)), tailtip=R5((48, 92, 70)),
    green=R5((84, 160, 66)), belly=R5((236, 170, 40)),
    foot=R5((134, 128, 132)), footfar=R5((92, 88, 94)),
    grey=R5((104, 108, 116), dk=(0.55, 0.3)), beak=R5((52, 52, 58), lt=(0.3, 0.5)),
    iris=R5((250, 214, 40)), pupil=R5((16, 12, 18)))


def main():
    sheet = Pic(CELL * FR, CELL)
    for f in range(FR): blit(sheet, kiwi(f, KIWI), f * CELL + PADC, PADC)
    write_tga(os.path.join(OUT, 'flyer_kiwi.tga'), sheet)
    write_png(os.path.join(OUT, 'flyer_kiwi.png'), sheet)
    print('drew kiwi')


if __name__ == '__main__':
    main()
