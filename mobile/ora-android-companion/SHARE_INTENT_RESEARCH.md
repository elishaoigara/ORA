# Share-to-ORA Native Integration

Source: [achorein/expo-share-intent](https://github.com/achorein/expo-share-intent), reviewed 2026-08-22.

The module receives user-initiated URLs, text, images, videos, and files from Android’s system share sheet and redirects into the app for review. Its published compatibility table lists **expo-share-intent 7.0+** for Expo SDK 56 and 5.0+ for Expo SDK 54. The project is implemented as an Expo native module and configuration plugin, so a newly published standalone Android build is required before it can receive external shares.

ORA must use the module only for deliberate shares. It must show a review sheet before calling the device-scoped capture endpoint and never silently ingest shared content.
