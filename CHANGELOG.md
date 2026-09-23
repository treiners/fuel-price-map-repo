# Changelog

## 0.8.0 - 2026-09-23

- Use explicit `Australia/Perth` time for FuelWatch tomorrow-feed handling.
- Check hourly at `HH:05` after 14:00 Perth time and validate the date returned
  by the RSS feed before exposing tomorrow trends.
- Add optional `person`/`device_tracker` location selection with a safe
  fallback to the configured coordinates or Home Assistant home zone.
- Refresh dynamic locations only on the existing scheduled/manual refreshes;
  location state changes do not continuously query FuelWatch.
- Make the example dashboard sizing adapt to viewport height and document
  desktop/mobile setup.

## Upgrade and release workflow

1. Update `manifest.json` and this changelog with the new semantic version.
2. Commit and push the changes.
3. Create a GitHub release whose tag exactly matches the manifest version
   (for example, `0.8.0`).
4. In HACS, update the integration and restart Home Assistant. If the version
   or release tag does not match, HACS may not offer the update reliably.

Existing config entries retain their static coordinates. Open the integration's
options to select a `person` or `device_tracker` when current-location
behavior is desired; the saved latitude/longitude remain the fallback.
