import sys
import subprocess
import tempfile
import time
from pathlib import Path
import xml.etree.ElementTree as ET


GOOGLE_EARTH_PATHS = [
    Path(r"C:\Program Files\Google\Google Earth Pro\client\googleearth.exe"),
    Path(r"C:\Program Files (x86)\Google\Google Earth Pro\client\googleearth.exe"),
    Path(r"C:\Program Files\Google\Google Earth Pro\googleearth.exe"),
    Path(r"C:\Program Files (x86)\Google\Google Earth Pro\googleearth.exe"),
]


def find_google_earth():
    for path in GOOGLE_EARTH_PATHS:
        if path.exists():
            return path

    return None


def create_kml(latitude, longitude, point_index):
    root = ET.Element(
        "kml",
        {"xmlns": "http://www.opengis.net/kml/2.2"},
    )

    document = ET.SubElement(root, "Document")

    name = ET.SubElement(document, "name")
    name.text = f"URBANFLOW Point {point_index + 1}"

    placemark = ET.SubElement(document, "Placemark")

    placemark_name = ET.SubElement(placemark, "name")
    placemark_name.text = f"URBANFLOW Point {point_index + 1}"

    description = ET.SubElement(placemark, "description")
    description.text = (
        f"URBANFLOW Point {point_index + 1}\n"
        f"Latitude: {latitude:.8f}\n"
        f"Longitude: {longitude:.8f}"
    )

    point = ET.SubElement(placemark, "Point")

    coordinates = ET.SubElement(point, "coordinates")
    coordinates.text = (
        f"{longitude:.8f},{latitude:.8f},0"
    )

    look_at = ET.SubElement(placemark, "LookAt")

    for tag, value in [
        ("longitude", longitude),
        ("latitude", latitude),
        ("altitude", 0),
        ("range", 500),
        ("tilt", 0),
        ("heading", 0),
    ]:
        element = ET.SubElement(look_at, tag)
        element.text = str(value)

    temp_directory = (
        Path(tempfile.gettempdir())
        / "urbanflow_google_earth"
    )

    temp_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        f"urbanflow_point_"
        f"{point_index}_"
        f"{int(time.time())}.kml"
    )

    kml_path = temp_directory / filename

    tree = ET.ElementTree(root)

    tree.write(
        kml_path,
        encoding="utf-8",
        xml_declaration=True,
    )

    return kml_path


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: launcher.py <latitude> <longitude> <point_index>"
        )
        sys.exit(1)

    try:
        latitude = float(sys.argv[1])
        longitude = float(sys.argv[2])
        point_index = int(sys.argv[3])
    except ValueError:
        print("Invalid coordinates or point index.")
        sys.exit(1)

    google_earth = find_google_earth()

    if google_earth is None:
        print(
            "Google Earth Pro was not found on this computer."
        )
        sys.exit(1)

    kml_path = create_kml(
        latitude,
        longitude,
        point_index,
    )

    subprocess.Popen(
        [
            str(google_earth),
            str(kml_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print(
        f"Google Earth Pro opened at URBANFLOW Point "
        f"{point_index + 1}."
    )


if __name__ == "__main__":
    main()