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

In addition to these main functionalities the plugin contains tools for data manipulation
(e.g. explode polygon to lines or split a line).

Please report issues preferably to Issues or to info@gispo.fi. The plugin is not actively developed,
but if you want to support the development or request a feature, do not hesitate to contact us.

Developed by **Gispo Ltd**.

## Installation instructions

1. Via official QGIS plugin repository: Launch QGIS and navigate to the plugins menu by selecting Plugins > Manage
and Install Plugins from the top menu. Go to All tab and search for Geodesic Tools and click Install Plugin!

2. From ZIP-file: Navigate to Releases and under the newest release's Assets section click kimu.Va.b.z.zip in order
to download the plugin as a ZIP file. Lauch QGIS and navigate to plugins menu (as in 1), but this time, go to
Install from ZIP tab, set the correct path to the ZIP file you just downloaded and click Install Plugin!

As a result, a new toolbar emerges into QGIS:
![plugin toolbar](/images/plugin_toolbar.png "Plugin toolbar")

## Usage

### Rectangular mapping

Practical example of the use case: User aims to map corner points for a rectangular building so that first
corner point of the building is mapped against the specified boundary line. The location of the first corner point is
36.2 meters (A measure) along the selected property boundary line and 27.8 meters (B measure) into the property. The building
consists of four corner points whose distances to each other (starting from first corner point located via A and
B measures) are: 8.2, 13.6, 8.2 and 13.6 meters.

1. Make sure that you have a line layer active in the Layers panel.
2. Utilize QGIS's selection tools to select (exactly one) line feature against which yuo want to start the rectangular mapping procedure:
![QGIS's selection toolbar](/images/qgis_selection_tools.png "QGIS's selection toolbar")

3. Click Rectangular mapping button -> the panel opens up into the right side of the QGIS.
4. In the panel, insert values for A and B measures to be applied. Press Enter.
- Give the A and B measures in coordinate reference system units (e.g. for EPG:3067 in meters)
- A measure specifies the distance you wish to move from the selected line feature's start / end point along
the selected line feature (or its extent)
- B measure specifies the distance you wish to move orthogonally from the chosen Point A
- A and/or B measures can be zero, too
5. In the panel, insert a list of values specifying the distances between rectangularly mapped points
- Give the distances in coordinate reference system units (e.g. for EPG:3067 in meters)
- Separate each distance value with comma
- Do not use any additional characters (e.g. spaces)
- This list can be left empty, too (if you just wish to locate Point B)
- Note that in order to rectangularly map X points, you only need to insert X-1 distances (in our practical example,
three inserted wall lengths specify the locations of all four building corner points)
- However, if you insert "an extra" distance in the list, it does not matter since the tool has a check preventing it from
mapping duplicate points
6. Select already existing file (e.g. geopackage) into which you wish to store the obtained result layer.

- The coordinate reference system of the file must match with the coordinate reference system of the active layer!
- You can leave this file path also empty

7. Click start / end point of the selected line feature to determine the point from which the tool will start the
rectangular mapping.
8. Answer to the questions the tool asks from you via a pop-up window.

In action:
![Rectangular mapping](/images/rectangular_mapping.gif "Rectangular mapping")

**Note.** The tool automatically enables suitable snapping configurations.

### Intersect line and circle

1. Make sure that you have a line layer active in the Layers panel.
2. Utilize QGIS's selection tools to select (exactly one) line feature whose intersection point with the implicitly defined circle you wish to determine:
![QGIS's selection toolbar](/images/qgis_selection_tools.png "QGIS's selection toolbar")

3. Click Intersect line and circle button -> the panel opens up into the right side of the QGIS.
4. In the panel, insert a value for the implicitly definable circle radius. Press Enter.

- Give the size of the radius in coordinate reference system units (e.g. for EPG:3067 in meters)

5. Click any point feature / vertex point visible in the map canvas to be used as a centroid of the implicitly definable circle.
6. Select already existing file (e.g. geopackage) into which you wish to store the obtained result point.

- The coordinate reference system of the file must match with the coordinate reference system of the active layer!
- You can leave this file path also empty

7. Answer to the question the tool asks from you via a pop-up window.

- If the line does not genuinely intersect with the implicitly defined circle (just touches it), the tool does not ask any questions but automatically produces the resulting scratch layer

In action:
![Intersect line and circle](/images/intersect_line_circle.gif "Intersect line and circle")

**Note.** The tool automatically enables suitable snapping configurations. However, if you want to be sure that QGIS snapped onto the right point feature / vertex point
in step 5, you can take a look at the attribute table of the resulting layer and compare the coordinates of the applied centroid with the coordinates of the point
you desired to utilize.

### Intersect lines

1. Make sure that you have a line layer active in the Layers panel.
2. Utilize QGIS's selection tools to select the feature(s) you wish to find the intersection point for (from the currently active layer):
![QGIS's selection toolbar](/images/qgis_selection_tools.png "QGIS's selection toolbar")

- The intersecting line features must belong to the same line layer! If the lines belong to different layers, you can always navigate to
Vector > Data Management Tools and use Merge Vector Layers tool
- If your line layer has MultiLineString type of features, consider using Explode Lines tool first!

3.Click Intersect lines button.

In action:
![Intersect lines](/images/intersect_lines.gif "Intersect lines")

**Note.** In QGIS, a temporary scratch file can easily be exported and made permanent.

### Displace line

1. Make sure that you have a line layer active in the Layers panel.
2. Click Displace line button -> the panel opens up into the right side of the QGIS.
3. In the panel, insert a value determining the distance you wish to move the line feature orthogonally. Press Enter.

- Give the displacement distance in coordinate reference system units (e.g. for EPG:3067 in meters)
- You can insert negative values too. Negative "distances" might be needed in situations where user has given the positive
displacement distance and the resulting line feature has appeared to the "wrong side" of the original line feature. In other words,
by replacing the displacement distance value with its opposite number, the displaced line feature will be mirrowed to the other side
of the original line feature

4. Click any line feature visible on the map canvas that you wish to displace.
5. Answer to the question the tool asks from you via a pop-up window.

In action:
![Displace line](/images/displace_line.gif "Displace line")
or
![Displace line 2](/images/displace_line2.gif "Displace line 2")

**Note.** In QGIS, a temporary scratch file can easily be exported and made permanent.

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
