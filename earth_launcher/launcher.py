import sys
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
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


def parse_arguments():
    """
    Supports both:

    1. Direct command:
       launcher.exe 28.6139 77.2090 33

    2. URBANFLOW protocol:
       launcher.exe "urbanflow://open?lat=28.6139&lon=77.2090&point=33"
    """

    if len(sys.argv) == 2:
        protocol_url = sys.argv[1]

        parsed = urlparse(protocol_url)

        if parsed.scheme.lower() != "urbanflow":
            raise ValueError("Invalid URBANFLOW protocol.")

        if parsed.netloc.lower() != "open":
            raise ValueError("Invalid URBANFLOW protocol action.")

        query = parse_qs(parsed.query)

        try:
            latitude = float(query["lat"][0])
            longitude = float(query["lon"][0])
            point_index = int(query["point"][0])
        except (KeyError, ValueError, IndexError):
            raise ValueError(
                "Invalid latitude, longitude or point index."
            )

    elif len(sys.argv) == 4:
        try:
            latitude = float(sys.argv[1])
            longitude = float(sys.argv[2])
            point_index = int(sys.argv[3])
        except ValueError:
            raise ValueError(
                "Invalid coordinates or point index."
            )

    else:
        raise ValueError(
            "Usage:\n"
            "launcher.exe <latitude> <longitude> <point_index>\n"
            "or\n"
            "launcher.exe \"urbanflow://open?lat=...&lon=...&point=...\""
        )

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude is outside the valid range.")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude is outside the valid range.")

    if point_index < 0:
        raise ValueError("Point index cannot be negative.")

    return latitude, longitude, point_index


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
    try:
        latitude, longitude, point_index = parse_arguments()
    except ValueError as error:
        print(error)
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