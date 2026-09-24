# Changelog

## 0.9.0 - 2026-09-24

- Finalise the responsive desktop/mobile dashboard layout and keep the map
  focus tied to the active home/tracker location sensor.
- Improve release metadata and documentation readiness for HACS installs and
  requirement checks.
- Keep the FuelWatch tomorrow-feed logic aligned to Perth time, validating that
  the RSS date is genuinely for Perth tomorrow before exposing the next-day
  change.
- Persist optional tracker configuration cleanly and stabilise registry-based
  entity IDs across upgrades.

## 0.8.4 - 2026-09-24

- Keep the complete example dashboard in one valid YAML document, including
  the Fuel Price Map settings popup, GPS toggle, and home history view.
- Keep the active-location entity as `focus_entity` only; it is no longer a
  visible map marker, avoiding its coordinate tooltip while preserving
  toggle-driven refocus.

## 0.8.3 - 2026-09-23

- Add the stable `sensor.fuel_price_map_active_location` map focus entity.
- Configure the example map with `focus_entity` and `focus_follow: refocus`;
  it recenters only after a successful location toggle, not on price refreshes.
- Include active home/tracker mode, source, latitude, and longitude attributes.

## 0.8.2 - 2026-09-23

- Add `fuel_price_map.toggle_location` and an example Bubble Card GPS
  sub-button to switch between home and the configured tracker at runtime.
- Validate tracker availability and coordinates before activating it; failed
  activations are logged without making a FuelWatch request.
- Keep the dashboard map center static because the external map card does not
  support dynamic recentering from this service.

## 0.8.1 - 2026-09-23

- Preserve an optional person/device tracker selection when reopening options.
- Treat an unset location entity as absent rather than passing `None` through
  Home Assistant's entity selector.
- Include the numeric next-day change in map marker labels, for example
  `+3.0c ▲` or `-2.0c ▼`.

Additional 0.8.1 note: map markers use station names as friendly names.
Linked table/map hover highlighting remains unsupported by the external cards.

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
   (for example, `0.8.1`).
4. In HACS, update the integration and restart Home Assistant. If the version
   or release tag does not match, HACS may not offer the update reliably.

Existing config entries retain their static coordinates. Open the integration's
options to select a `person` or `device_tracker` when current-location
behavior is desired; the saved latitude/longitude remain the fallback.
