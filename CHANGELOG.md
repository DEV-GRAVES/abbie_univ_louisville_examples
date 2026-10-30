# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-10-30
### Added
- Change log tab in the HTML report, parsed directly from this file (CHG-118)
- Team communication tab rendered from docs/team_communication.json (CHG-118)
- HTML-escaping of team message text before it is embedded in the report

## [2.0.0] - 2026-10-14
### Changed
- BREAKING: report output is now a self-contained interactive HTML page instead of CSV (CHG-104)
- BREAKING: --out flag now expects a .html path
### Added
- Daily fill-rate trend chart with per-site filter and target line
- Sortable site detail table with red/amber/green status pills

## [1.2.0] - 2026-09-30
### Added
- On-time ship KPI calculated alongside fill rate (CHG-097)

## [1.1.1] - 2026-09-18
### Fixed
- Divide-by-zero when a site had no ordered units on a given day (CHG-091)
- Shipped quantity greater than ordered quantity is now clamped instead of inflating fill rate

## [1.1.0] - 2026-09-12
### Added
- SKU-family grouping for fill rate (CHG-088)

## [1.0.0] - 2026-09-02
### Added
- Initial release: fill rate by warehouse site from an order-line CSV
