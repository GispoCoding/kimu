# KiMu
![tests](https://github.com/GispoCoding/kimu/workflows/Tests/badge.svg)
[![codecov.io](https://codecov.io/github/GispoCoding/kimu/coverage.svg?branch=master)](https://codecov.io/github/GispoCoding/kimu?branch=master)
![release](https://github.com/GispoCoding/kimu/workflows/Release/badge.svg)
[![GPLv3 license](https://img.shields.io/badge/License-GPLv3-blue.svg)](http://perso.crans.org/besson/LICENSE.html)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)

This QGIS3 plugin containing geodesic tools and is developed for
- rectangular mapping
- finding intersection point of a line and a circle
- finding intersection point of two lines
- displacing a line feature

In addition to these main functionalities the plugin contains tools for data manipulation (e.g. explode polygon to lines or split a line).

Please report issues preferably to Issues or to info@gispo.fi. The plugin is not actively developed, but if you want to support the development or request a feature, do not hesitate to contact us.

Developed by **Gispo Ltd**.

## Installation instructions

1. Via official QGIS plugin repository: Launch QGIS and navigate to the plugins menu by selecting Plugins > Manage and Install Plugins from the top menu.
Go to All tab and search for Geodesic Tools and click Install Plugin!

2. From ZIP-file: Navigate to Releases and under the newest release's Assets section click kimu.Va.b.z.zip in order to download the plugin as a ZIP file.
Lauch QGIS and navigate to plugins menu (as in 1), but this time, go to Install from ZIP tab, set the correct path to the ZIP file you just downloaded and click Install Plugin!

As a result, a new toolbar emerges:
![plugin toolbar](/images/plugin_toolbar.png "Plugin toolbar")

## Usage

### Rectangular mapping

### Intersect line and circle

### Intersect lines

### Displace line

### Explode polygon

1. Make sure that you have a polygon layer active in the Layers panel.
2. Utilize QGIS's selection tools to select the feature(s) you wish to explode (from the currently active layer):
![QGIS's selection toolbar](/images/qgis_selection_tools.png "QGIS's selection toolbar")

- It is possible to select all the features in the layer, too!
3.Click Explode polygon button.

In action:

![Explode polygon](/images/explode_polygon.gif "Explode polygon")

**Note.** In QGIS, a temporary scratch file can easily be exported and made permanent.

### Explode line(s)

1. Make sure that you have a line layer active in the Layers panel.
2. Utilize QGIS's selection tools to select the feature(s) you wish to explode (from the currently active layer):
![QGIS's selection toolbar](/images/qgis_selection_tools.png "QGIS's selection toolbar")

- It is possible to select all the features in the layer, too!
3.Click Explode line(s) button.

In action:
![Explode lines](/images/explode_lines.gif "Explode lines")

**Note.** In QGIS, a temporary scratch file can easily be exported and made permanent.

### Explode line(s) to points

1. Make sure that you have a line layer active in the Layers panel.
2. Utilize QGIS's selection tools to select the feature(s) you wish to explode (from the currently active layer):
![QGIS's selection toolbar](/images/qgis_selection_tools.png "QGIS's selection toolbar")

- It is possible to select all the features in the layer, too!
3.Click Explode line(s) to points button.

In action:
![Explode line to points](/images/explode_lines_to_points.gif "Explode line to points")

**Note.** In QGIS, a temporary scratch file can easily be exported and made permanent.

### Split line

1. Make sure that you have a line layer active in the Layers panel.
2. Click Split line button -> the panel opens up into the right side of the QGIS.
3. In the panel, insert a value determining into how many equally long pieces you wish the selected line feature to split. Press Enter.
4. Click the line feature you wish to split.

In action:
![Split line](/images/split_line.gif "Split line")

**Note.** In QGIS, a temporary scratch file can easily be exported and made permanent.

## Development

Refer to [development](docs/development.md) for developing this QGIS3 plugin.

## License
This plugin is licenced with
[GNU General Public License, version 3](https://www.gnu.org/licenses/gpl-3.0.html).
See [LICENSE](LICENSE) for more information.
