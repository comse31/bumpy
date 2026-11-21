# Serve the Defold HTML5 (wasm-web) bundle with nginx.
#
# Build context is the repository root. The game bundle must be produced first:
#   node tools/api_bundle_html5.js --output dist/web
#
# Then build and run the image:
#   docker build -f docker/Dockerfile -t bumpy-web .
#   docker run --rm -p 8080:80 bumpy-web
# and open http://localhost:8080

FROM nginx:1.27-alpine

# Custom server configuration (WASM mime type, caching, SPA fallback)
COPY docker/nginx.conf /etc/nginx/nginx.conf

# HTML5 bundle produced by bob (build + bundle for platform wasm-web, archive=true)
COPY dist/web/bumpy/ /usr/share/nginx/html/

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
