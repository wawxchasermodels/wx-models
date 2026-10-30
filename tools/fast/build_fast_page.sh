#!/bin/bash
# Build the hidden fast page (branch "fast" of Pages project wx-forecast-maps; data comes from R2 via functions/d)
set -e; cd "$(dirname "$0")"; SRC=site
rm -rf public; mkdir -p public/fonts
cp $SRC/viewer.js public/; cp $SRC/fonts/Montserrat-sub.woff2 public/fonts/
sed -e 's#<script src="viewer.js"></script>#<script>window.WX_DATA="/d/"</script><script src="viewer.js"></script>#' \
    -e 's#,url(fonts/Montserrat.ttf) format("truetype")##' \
    -e 's#<head>#<head><meta name="robots" content="noindex,nofollow">#' $SRC/index.html > public/index.html
printf '/*\n  X-Robots-Tag: noindex\n/viewer.js\n  Cache-Control: no-cache\n/index.html\n  Cache-Control: no-cache\n/fonts/*\n  Cache-Control: public, max-age=31536000, immutable\n' > public/_headers
printf '{"version":1,"include":["/d/*"],"exclude":[]}\n' > public/_routes.json
