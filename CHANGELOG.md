# CHANGELOG

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [2.0.3] - 2022
- TBD

## [2.0.2] - 2022-11-10
### Changed
- Features can now be selected from different layers in intersect lines and intersect circle and line tools
- Points can be used as input for intersect lines tool
- Numeric fields allow now input with precision of 10 decimals (instead of 3)
- Minor modifications to log messages and layer output names

### Fixed
- Rectangular mapping tool doesn't fail anymore with some inputs
- Errors are not thrown anymore when non-vector (e.g. raster) files are added to same project

## [2.0.1] - 2022-10-13
###
- To be documented

## [0.2.1] - 2021-09-06
### Added
- First unit tests.

### Fixed
- Check if color ramp "Turbo" exists, otherwise use last available ramp.

## [0.2.0] - 2021-09-03
### Added
- Apply different colors for segments of split line to help distinguish them.

### Changed
- Require user to select a single polygon to explode.

### Fixed
- Don't create nodes to midpoints of arcs.
- Add backwards compatibility with QGIS 3.16 on QgsLineSymbol properties.

## [0.1.0] - 2021-06-21

- Initial release with Explode and Split tools.

[0.2.1]: https://github.com/GispoCoding/kimu/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/GispoCoding/kimu/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/GispoCoding/kimu/releases/tag/v0.1.0
