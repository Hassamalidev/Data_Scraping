-- migrate:up
-- Source registry only. Rows are added here once a source has passed inspection
-- (CLAUDE.md Phase 3). No business rows are ever seeded.
INSERT INTO sources (id, name, type, base_url, trust_rank, interval_hours, terms_notes, attribution)
VALUES (
  'osm_overpass',
  'OpenStreetMap (Overpass API)',
  'open_data',
  'https://overpass-api.de/api/interpreter',
  3,
  24,
  'Open Database License (ODbL) 1.0. Attribution required.',
  '© OpenStreetMap contributors (ODbL)'
);

-- migrate:down
DELETE FROM sources WHERE id = 'osm_overpass';
