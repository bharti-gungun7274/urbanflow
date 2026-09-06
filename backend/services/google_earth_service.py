from pathlib import Path
import os
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET


class GoogleEarthService:

    POSSIBLE_PATHS = [
        Path(
            r"C:\Program Files\Google\Google Earth Pro\client\googleearth.exe"
        ),
        Path(
            r"C:\Program Files (x86)\Google\Google Earth Pro\client\googleearth.exe"
        ),
        Path(
            r"C:\Program Files\Google\Google Earth Pro\googleearth.exe"
        ),
        Path(
            r"C:\Program Files (x86)\Google\Google Earth Pro\googleearth.exe"
        ),
    ]

    @classmethod
    def find_executable(cls):
        for path in cls.POSSIBLE_PATHS:
            if path.exists():
                return path

        path_variable = os.environ.get(
            "PATH",
            ""
        )

        for directory in path_variable.split(
            os.pathsep
        ):
            if not directory:
                continue

            candidate = (
                Path(directory)
                / "googleearth.exe"
            )

            if candidate.exists():
                return candidate

        return None

    @staticmethod
    def create_kml(
        longitude,
        latitude,
        point_index,
        dw_class_name=None,
        reference_class_name=None,
    ):

        root = ET.Element(
            "kml",
            {
                "xmlns":
                    "http://www.opengis.net/kml/2.2"
            },
        )

        document = ET.SubElement(
            root,
            "Document"
        )

        name = ET.SubElement(
            document,
            "name"
        )

        name.text = (
            f"URBANFLOW Point "
            f"{point_index + 1}"
        )

        placemark = ET.SubElement(
            document,
            "Placemark"
        )

        placemark_name = ET.SubElement(
            placemark,
            "name"
        )

        placemark_name.text = (
            f"URBANFLOW Point "
            f"{point_index + 1}"
        )

        description = ET.SubElement(
            placemark,
            "description"
        )

        details = [
            f"URBANFLOW Point {point_index + 1}",
            f"Latitude: {latitude:.8f}",
            f"Longitude: {longitude:.8f}",
        ]

        if dw_class_name:
            details.append(
                f"Dynamic World: "
                f"{dw_class_name}"
            )

        if reference_class_name:
            details.append(
                f"Reference: "
                f"{reference_class_name}"
            )

        description.text = "\n".join(
            details
        )

        point = ET.SubElement(
            placemark,
            "Point"
        )

        coordinates = ET.SubElement(
            point,
            "coordinates"
        )

        coordinates.text = (
            f"{longitude:.8f},"
            f"{latitude:.8f},0"
        )

        look_at = ET.SubElement(
            placemark,
            "LookAt"
        )

        for tag, value in [
            ("longitude", longitude),
            ("latitude", latitude),
            ("altitude", 0),
            ("range", 500),
            ("tilt", 0),
            ("heading", 0),
        ]:
            element = ET.SubElement(
                look_at,
                tag
            )
            element.text = str(value)

        temp_directory = (
            Path(tempfile.gettempdir())
            / "urbanflow_google_earth"
        )

        temp_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        filename = (
            f"urbanflow_point_"
            f"{point_index}_"
            f"{int(time.time())}.kml"
        )

        kml_path = (
            temp_directory
            / filename
        )

        tree = ET.ElementTree(root)

        tree.write(
            kml_path,
            encoding="utf-8",
            xml_declaration=True,
        )

        return kml_path

    @classmethod
    def open_point(
        cls,
        longitude,
        latitude,
        point_index,
        dw_class_name=None,
        reference_class_name=None,
    ):

        executable = (
            cls.find_executable()
        )

        if executable is None:
            raise FileNotFoundError(
                "Google Earth Pro was not found."
            )

        kml_path = cls.create_kml(
            longitude,
            latitude,
            point_index,
            dw_class_name,
            reference_class_name,
        )

        subprocess.Popen(
            [
                str(executable),
                str(kml_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return {
            "status": "success",
            "message":
                "Google Earth Pro opened at the current validation point.",
            "point_index":
                point_index,
            "longitude":
                longitude,
            "latitude":
                latitude,
        }