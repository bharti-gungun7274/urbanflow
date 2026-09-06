from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from pyproj import Transformer


class RasterService:

    def __init__(
        self,
        lulc_path: str | None = None,
        reference_path: str | None = None
    ):
        self.lulc_path = (
            Path(lulc_path)
            if lulc_path
            else None
        )

        self.reference_path = (
            Path(reference_path)
            if reference_path
            else None
        )

    # =========================================================
    # SET RASTER PATHS
    # =========================================================

    def set_paths(
        self,
        lulc_path,
        reference_path
    ):
        self.lulc_path = Path(lulc_path)
        self.reference_path = Path(reference_path)

    # =========================================================
    # VALIDATE FILES
    # =========================================================

    def validate_files(self):

        if self.lulc_path is None:
            raise ValueError(
                "LULC raster has not been loaded."
            )

        if self.reference_path is None:
            raise ValueError(
                "Reference raster has not been loaded."
            )

        if not self.lulc_path.exists():
            raise FileNotFoundError(
                f"LULC raster not found: {self.lulc_path}"
            )

        if not self.reference_path.exists():
            raise FileNotFoundError(
                f"Reference raster not found: {self.reference_path}"
            )

    # =========================================================
    # GET RASTER PATH
    # =========================================================

    def _get_path(self, kind):

        if kind == "lulc":
            return self.lulc_path

        if kind == "reference":
            return self.reference_path

        raise ValueError(
            f"Unknown raster kind: {kind}"
        )

    # =========================================================
    # RASTER INFORMATION
    # =========================================================

    def get_info(self, kind):

        self.validate_files()

        path = self._get_path(kind)

        with rasterio.open(path) as src:

            return {
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "dtype": str(src.dtypes[0]),
                "crs": str(src.crs),
                "bounds": {
                    "left": src.bounds.left,
                    "bottom": src.bounds.bottom,
                    "right": src.bounds.right,
                    "top": src.bounds.top
                },
                "nodata": src.nodata,
                "transform": list(src.transform)
            }

    # =========================================================
    # LON/LAT → RASTER PIXEL
    # =========================================================

    def _lonlat_to_pixel(
        self,
        src,
        longitude,
        latitude
    ):

        transformer = Transformer.from_crs(
            "EPSG:4326",
            src.crs,
            always_xy=True
        )

        x, y = transformer.transform(
            longitude,
            latitude
        )

        row, column = src.index(
            x,
            y
        )

        return row, column

    # =========================================================
    # READ WINDOW
    # =========================================================

    def read_window(
        self,
        kind,
        longitude,
        latitude,
        radius_pixels=100
    ):

        self.validate_files()

        path = self._get_path(kind)

        with rasterio.open(path) as src:

            # -------------------------------------------------
            # Convert point coordinates to raster pixel
            # -------------------------------------------------

            row, column = self._lonlat_to_pixel(
                src,
                longitude,
                latitude
            )

            # -------------------------------------------------
            # Calculate window
            # -------------------------------------------------

            col_off = max(
                0,
                column - radius_pixels
            )

            row_off = max(
                0,
                row - radius_pixels
            )

            right = min(
                src.width,
                column + radius_pixels + 1
            )

            bottom = min(
                src.height,
                row + radius_pixels + 1
            )

            width = right - col_off
            height = bottom - row_off

            window = Window(
                col_off=col_off,
                row_off=row_off,
                width=width,
                height=height
            )

            # -------------------------------------------------
            # Read raster
            # -------------------------------------------------

            if kind == "lulc":

                data = src.read(
                    1,
                    window=window
                )

            else:

                band_count = min(
                    src.count,
                    4
                )

                data = src.read(
                    list(
                        range(
                            1,
                            band_count + 1
                        )
                    ),
                    window=window
                )

            # -------------------------------------------------
            # EXACT POINT POSITION INSIDE WINDOW
            # -------------------------------------------------

            point_column = (
                column - col_off
            )

            point_row = (
                row - row_off
            )

            # -------------------------------------------------
            # Return everything frontend needs
            # -------------------------------------------------

            return {

                "data": data,

                # Original raster pixel
                "row": int(row),
                "column": int(column),

                # Window information
                "window": {
                    "col_off": int(col_off),
                    "row_off": int(row_off),
                    "width": int(width),
                    "height": int(height)
                },

                # Exact point location
                # INSIDE returned raster
                "point_column": int(
                    point_column
                ),

                "point_row": int(
                    point_row
                ),

                "width": int(width),
                "height": int(height),

                "crs": str(src.crs),

                "transform": list(
                    src.window_transform(window)
                )
            }

    # =========================================================
    # LULC WINDOW
    # =========================================================

    def read_lulc_window(
        self,
        longitude,
        latitude,
        radius_pixels=100
    ):

        return self.read_window(
            "lulc",
            longitude,
            latitude,
            radius_pixels
        )

    # =========================================================
    # REFERENCE WINDOW
    # =========================================================

    def read_reference_window(
        self,
        longitude,
        latitude,
        radius_pixels=100
    ):

        return self.read_window(
            "reference",
            longitude,
            latitude,
            radius_pixels
        )