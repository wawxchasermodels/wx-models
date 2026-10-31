#!/bin/bash
# Build the hidden fast page (branch "fast" of Pages project wx-forecast-maps; data comes from R2 via functions/d)
set -e; cd "$(dirname "$0")"; SRC=site
rm -rf public; mkdir -p public/fonts
mkdir -p public/obs; OBS=${OBS_SRC:-../../web/forecast/obs}; cp $OBS/obs.js $OBS/obs.css $OBS/basemap.json public/obs/   # live obs module (read-only copy of the old site's)
cp $SRC/viewer.js public/; cp $SRC/fonts/Montserrat-sub.woff2 public/fonts/
# meteograms page (10-30): own page + read-only copies of the old site's page styles and fonts (same layout as the old Meteograms tab)
OLD=${OLD_SRC:-../../web/forecast}; mkdir -p public/old/fonts; cp $OLD/base.css $OLD/forecast.css public/old/; cp $OLD/fonts/*.ttf public/old/fonts/
cp $SRC/meteograms.js public/
sed -e 's#<script src="meteograms.js"></script>#<script>window.WX_DATA="/d/"</script><script src="meteograms.js"></script>#' \
    -e 's#<head>#<head><meta name="robots" content="noindex,nofollow">#' $SRC/meteograms.html > public/meteograms.html
sed -e 's#<script src="viewer.js#<script>window.WX_DATA="/d/"</script><script src="viewer.js#' \
    -e 's#,url(fonts/Montserrat.ttf) format("truetype")##' \
    -e 's#<head>#<head><meta name="robots" content="noindex,nofollow">#' $SRC/index.html > public/index.html
# WA Maps (10-31): page + kit (static layers made by tools/fast/wamaps/build_kit.py + package_kit.py)
cp $SRC/wamaps.js public/; cp -r $SRC/wamaps public/
sed -e 's#<script src="wamaps.js"></script>#<script>window.WX_DATA="/d/"</script><script src="wamaps.js"></script>#' \
    -e 's#,url(fonts/Montserrat.ttf) format("truetype")##' \
    -e 's#<head>#<head><meta name="robots" content="noindex,nofollow">#' $SRC/wamaps.html > public/wamaps.html
printf '/*\n  X-Robots-Tag: noindex\n/viewer.js\n  Cache-Control: no-cache\n/index.html\n  Cache-Control: no-cache\n/meteograms*\n  Cache-Control: no-cache\n/wamaps.*\n  Cache-Control: no-cache\n/fonts/*\n  Cache-Control: public, max-age=31536000, immutable\n' > public/_headers
printf '{"version":1,"include":["/d/*"],"exclude":[]}\n' > public/_routes.json
