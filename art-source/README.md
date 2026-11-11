# Art source

`make_art.py` draws all of Taxi Time's art (the 8 `.tga` files in `TaxiTime\media\`, plus the 2 old flyer_alliance/horde sheets that are no longer shipped) from shapes typed into the script. No outside or Blizzard art is used.

Run `python make_art.py` (plain Python 3, no extra packages). It writes the 10 files to `out\` next to the script. Copy them into `TaxiTime\media\` yourself. `python make_art.py all` also writes both design looks and preview pictures.

| File | Size | What |
|---|---|---|
| `flyer_gryphon.tga`, `flyer_windrider.tga`, `flyer_bat.tga`, `flyer_hippogryph.tga` | 512x128 | Painted flyer sheets (cartoon style / fallback for the 3D model): 4 frames of 128x128, frame i at tex coords (i*0.25, (i+1)*0.25, 0, 1) |
| `flyer_alliance.tga`, `flyer_horde.tga` | 256x64 | Older small flyer sheets: 4 frames of 64x64 |
| `bar_fill.tga` | 256x32 | Bar fill |
| `bar_frame.tga` | 256x64 | Bar frame |
| `cloud.tga` | 64x32 | Cloud |
| `sparkle.tga` | 128x32 | Sparkle, 4 frames of 32x32 |
