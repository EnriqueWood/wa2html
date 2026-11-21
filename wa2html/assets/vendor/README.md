# Third-party code

## lottie-web

- File: `lottie.min.js`, the unmodified "light" player build (SVG renderer, no expressions).
- Version: 5.12.2
- Source: https://cdnjs.cloudflare.com/ajax/libs/lottie-web/5.12.2/lottie_light.min.js
  (identical to `build/player/lottie_light.min.js` in the `lottie-web@5.12.2` npm package)
- SHA-256: `23cd2c01be3d4da8bb664645d03afaff40879c62dc5f8dfe075ab3aa35c108f3`
- Licence: MIT, see `LICENSE-lottie-web.md`. Project: https://github.com/airbnb/lottie-web

wa2html inlines it into generated pages that contain WhatsApp animated stickers (`.was` files,
which are Lottie animations), together with a comment carrying the copyright notice.
