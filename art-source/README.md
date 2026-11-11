# Art source

Two scripts draw all of Taxi Time's art (the 8 `.tga` files in `TaxiTime\media\`) from shapes typed into the scripts. No outside or Blizzard art is used. Both are plain Python 3 (no extra packages) and write to `out\` next to the scripts. Copy the files into `TaxiTime\media\` yourself.

| Script | Makes |
|---|---|
| `make_flyers_v3b.py` | The 4 flyer sheets that ship: `flyer_gryphon.tga`, `flyer_windrider.tga`, `flyer_bat.tga`, `flyer_hippogryph.tga` (pixel art, 96x96 pixel grid per frame). `python make_flyers_v3b.py previews` also writes preview pictures to `out\previews\`. |
| `make_art.py` | `bar_fill.tga`, `bar_frame.tga`, `cloud.tga`, `sparkle.tga`. Run `python make_art.py` (`all` also writes design looks and previews). |

**Note:** `make_art.py` still also writes older flyer sheets (`flyer_gryphon/windrider/bat/hippogryph.tga`, the round-2 cartoon look, plus the unused `flyer_alliance/horde.tga`). Those flyer outputs are replaced by `make_flyers_v3b.py`: don't copy them into `media\`. Both scripts write to the same `out\` folder, so run `make_flyers_v3b.py` last (or only copy the 4 flyer files right after running it).

| File | Size | What |
|---|---|---|
| `flyer_gryphon.tga`, `flyer_windrider.tga`, `flyer_bat.tga`, `flyer_hippogryph.tga` | 512x128 | Pixel-art flyer sheets (from `make_flyers_v3b.py`): 4 frames of 128x128, frame i at tex coords (i*0.25, (i+1)*0.25, 0, 1), order wings up, going down, down, going up. Each 96x96 drawing sits centred 1:1 in its 128 cell, so it is crisp at 128 px on the bar. |
| `bar_fill.tga` | 256x32 | Bar fill |
| `bar_frame.tga` | 256x64 | Bar frame |
| `cloud.tga` | 64x32 | Cloud |
| `sparkle.tga` | 128x32 | Sparkle, 4 frames of 32x32 |
