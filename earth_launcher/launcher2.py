import os
import sys
import tempfile
import subprocess
import ctypes
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import xml.etree.ElementTree as ET


PROTOCOL_NAME = "urbanflow"


def find_google_earth():
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) /
        "Google" / "Google Earth Pro" / "client" / "googleearth.exe",

        Path(os.environ.get("PROGRAMFILES(X86)", "")) /
        "Google" / "Google Earth Pro" / "client" / "googleearth.exe",

        Path(os.environ.get("LOCALAPPDATA", "")) /
        "Google" / "Google Earth Pro" / "client" / "googleearth.exe",

        Path(os.environ.get("LOCALAPPDATA", "")) /
        "Google" / "Google Earth Pro" / "client" / "googleearth.exe",
    ]

    for path in candidates:
        if path.exists():
            return path

    return None


def create_kml(latitude, longitude, point_id):
    kml = ET.Element(
        "kml",
        {
            "xmlns": "http://www.opengis.net/kml/2.2"
        }
    )

    document = ET.SubElement(kml, "Document")

    name = ET.SubElement(document, "name")
    name.text = f"URBANFLOW Point {point_id + 1}"

    placemark = ET.SubElement(document, "Placemark")

    pm_name = ET.SubElement(placemark, "name")
    pm_name.text = f"Validation Point {point_id + 1}"

    description = ET.SubElement(placemark, "description")
    description.text = (
        f"URBANFLOW validation point {point_id + 1}"
    )

    point = ET.SubElement(placemark, "Point")

    coordinates = ET.SubElement(point, "coordinates")
    coordinates.text = (
        f"{longitude},{latitude},0"
    )

    look_at = ET.SubElement(document, "LookAt")

    look_longitude = ET.SubElement(
        look_at,
        "longitude"
    )
    look_longitude.text = str(longitude)

    look_latitude = ET.SubElement(
        look_at,
        "latitude"
    )
    look_latitude.text = str(latitude)

    look_altitude = ET.SubElement(
        look_at,
        "altitude"
    )
    look_altitude.text = "0"

    range_element = ET.SubElement(
        look_at,
        "range"
    )
    range_element.text = "1000"

    tilt = ET.SubElement(
        look_at,
        "tilt"
    )
    tilt.text = "0"

    heading = ET.SubElement(
        look_at,
        "heading"
    )
    heading.text = "0"

    root = ET.ElementTree(kml)

    temp_dir = Path(
        tempfile.gettempdir()
    ) / "URBANFLOW"

    temp_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    kml_path = (
        temp_dir /
        f"urbanflow_point_{point_id}.kml"
    )

    root.write(
        kml_path,
        encoding="utf-8",
        xml_declaration=True
    )

    return kml_path


def bring_google_earth_to_front():
    try:
        user32 = ctypes.windll.user32

        SW_RESTORE = 9

        def enum_callback(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True

            length = user32.GetWindowTextLengthW(hwnd)

            if length == 0:
                return True

            buffer = ctypes.create_unicode_buffer(
                length + 1
            )

            user32.GetWindowTextW(
                hwnd,
                buffer,
                length + 1
            )

            title = buffer.value.lower()

            if (
                "google earth" in title
                or "google earth pro" in title
            ):
                user32.ShowWindow(
                    hwnd,
                    SW_RESTORE
                )

                user32.SetForegroundWindow(
                    hwnd
                )

            return True

        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.c_void_p,
            ctypes.c_void_p
        )

        callback = callback_type(enum_callback)

        user32.EnumWindows(
            callback,
            0
        )

    except Exception:
        pass


def open_google_earth(latitude, longitude, point_id):
    earth_exe = find_google_earth()

    if earth_exe is None:
        print(
            "ERROR: Google Earth Pro was not found."
        )
        return False

    kml_path = create_kml(
        latitude,
        longitude,
        point_id
    )

    print(
        f"Opening validation point {point_id + 1}"
    )

    try:
        subprocess.Popen(
            [
                str(earth_exe),
                str(kml_path)
            ],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )

        import time
        time.sleep(2)

        bring_google_earth_to_front()

        print(
            "Google Earth Pro opened successfully."
        )

        return True

    except Exception as error:
        print(
            f"ERROR: Could not open Google Earth Pro: {error}"
        )
        return False


def parse_protocol_url(url):
    parsed = urlparse(url)

    if parsed.scheme.lower() != PROTOCOL_NAME:
        return None

    if parsed.netloc.lower() != "open":
        return None

    params = parse_qs(parsed.query)

    try:
        latitude = float(
            params["lat"][0]
        )

        longitude = float(
            params["lon"][0]
        )

        point_id = int(
            params["point"][0]
        )

    except (
        KeyError,
        ValueError,
        TypeError
    ):
        return None

    return (
        latitude,
        longitude,
        point_id
    )


def main():
    print()
    print(
        "URBANFLOW Google Earth Pro Launcher"
    )
    print(
        "-----------------------------------"
    )

    if len(sys.argv) < 2:
        print(
            "ERROR: No URBANFLOW URL was received."
        )
        input(
            "Press Enter to close..."
        )
        return 1

    url = sys.argv[1]

    values = parse_protocol_url(
        url
    )

    if values is None:
        print(
            "ERROR: Invalid URBANFLOW URL."
        )
        print(url)
        input(
            "Press Enter to close..."
        )
        return 1

    latitude, longitude, point_id = values

    print(
        f"Latitude : {latitude}"
    )

    print(
        f"Longitude: {longitude}"
    )

    print(
        f"Point ID : {point_id + 1}"
    )

    success = open_google_earth(
        latitude,
        longitude,
        point_id
    )

    if success:
        print()
        print(
            "[OK] Google Earth Pro opened successfully."
        )
    else:
        print()
        print(
            "[ERROR] Google Earth Pro could not be opened."
        )

    input(
        "Press Enter to close..."
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())