# Brand assets

Generated files live in `src/busemann/resources/brand/`. To regenerate, run from that folder:

```
python ../../../../tools/brand/make_logo.py        # logo SVG variants
python ../../../../tools/brand/make_lockup_and_icon.py   # lockups + app icon (overwrites app_icon*.svg)
node ../../../../tools/brand/render_pngs.js        # PNGs (needs node + playwright)
python ../../../../tools/brand/render_welcome_hero.py   # welcome image (numpy, scipy, matplotlib)
```
Then rebuild `busemann.ico` from the app_icon PNGs (Pillow, sizes 16-256).

| File | Use |
|---|---|
| logo.svg | main mark, light backgrounds, 48 px and up |
| logo_small.svg | 32 px and below (no faint Mach waves, thicker shock) |
| logo_white.svg | on dark or blue backgrounds |
| logo_mono.svg | one colour |
| logo_lockup.svg / _1x _2x _4x.png | logo with title and tagline, light backgrounds |
| logo_lockup_white.svg / _2x.png | logo with title, dark backgrounds |
| logo_lockup_stacked.svg / _2x.png | mark above title (README, splash) |
| app_icon*.svg / app_icon_*.png | window and taskbar icon: the logo on a light tile |
| busemann.ico | Windows icon, 16-256 px, for the .exe and installer |
| welcome_hero.png / welcome_hero_520.png | welcome window image (2x and 1x) |
