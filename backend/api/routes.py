from pathlib import Path
import shutil
import json

import pandas as pd

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Depends,
)

from pydantic import BaseModel

from backend.auth_dependency import get_current_user
from backend.database import SessionLocal
from backend.models import ValidationRecord, ValidationHistory

from backend.services.raster_service import RasterService

from backend.services.validation_service import (
    prepare_points,
    calculate_metrics,
    update_reference_class,
)

from backend.services.google_earth_service import (
    GoogleEarthService,
)

from backend.services.history_service import (
    load_history,
    save_history_record,
)


# ============================================================
# API ROUTER
# ============================================================

router = APIRouter(
    prefix="/api",
    dependencies=[Depends(get_current_user)],
)


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

PROJECT_DATA = BASE_DIR / "project_data"
OUTPUT_DIR = BASE_DIR / "outputs"

PROJECT_DATA.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# REQUEST MODELS
# ============================================================

class ReferenceUpdate(BaseModel):
    reference_class: int
    reference_source: str = ""


class ValidationRequest(BaseModel):
    reference_class: int
    reference_source: str = ""


# ============================================================
# PROJECT STATE
# ============================================================

class ProjectState:

    def __init__(self):
        self.area = ""
        self.year = ""
        self.lulc_path = None
        self.reference_path = None
        self.points_path = None
        self.points = pd.DataFrame()
        self.raster = RasterService()


state = ProjectState()


PROJECT_STATE_FILE = (
    PROJECT_DATA
    / "current"
    / "project_state.json"
)


# ============================================================
# VALIDATION HELPERS
# ============================================================

def _validated_indices():

    if not state.area or not state.year:
        return set()

    db = SessionLocal()

    try:

        records = (
            db.query(
                ValidationRecord.point_id
            )
            .filter(
                ValidationRecord.area == state.area,
                ValidationRecord.year == int(
                    state.year
                ),
            )
            .all()
        )

        return {
            int(record.point_id)
            for record in records
        }

    finally:

        db.close()


def _apply_database_validations(
    df: pd.DataFrame
) -> pd.DataFrame:

    """
    Restore validated reference classes and sources
    directly from PostgreSQL.

    PostgreSQL is the single source of truth
    for validation data.

    Old JSON validation-session values are NOT used
    to overwrite the dataframe.
    """

    if (
        df.empty
        or not state.area
        or not state.year
    ):
        return df

    db = SessionLocal()

    try:

        records = (
            db.query(
                ValidationRecord
            )
            .filter(
                ValidationRecord.area == state.area,
                ValidationRecord.year == int(
                    state.year
                ),
            )
            .all()
        )

        for record in records:

            point_id = int(
                record.point_id
            )

            if point_id not in df.index:
                continue

            df.at[
                point_id,
                "Reference_Class"
            ] = int(
                record.reference_class
            )

            df.at[
                point_id,
                "Reference_Source"
            ] = str(
                record.reference_source
            )

        return df

    finally:

        db.close()


# ============================================================
# PROJECT RESTORE
# ============================================================

def _restore_project_if_possible():

    if (
        not PROJECT_STATE_FILE.exists()
        or not state.points.empty
    ):
        return

    try:

        data = json.loads(
            PROJECT_STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        current = (
            PROJECT_DATA
            / "current"
        )

        lulc = (
            current
            / data["lulc_file"]
        )

        reference = (
            current
            / data["reference_file"]
        )

        points = (
            current
            / data["points_file"]
        )

        if not (
            lulc.exists()
            and reference.exists()
            and points.exists()
        ):
            return

        df = prepare_points(
            pd.read_csv(points)
        )

        state.area = str(
            data["area"]
        )

        state.year = str(
            data["year"]
        )

        # IMPORTANT:
        # Restore validation labels from PostgreSQL,
        # not from the old JSON session.
        df = _apply_database_validations(
            df
        )

        state.lulc_path = lulc
        state.reference_path = reference
        state.points_path = points
        state.points = df

        state.raster.set_paths(
            str(lulc),
            str(reference)
        )

    except Exception:
        return


# ============================================================
# HEALTH
# ============================================================

@router.get("/health")
def health():

    return {
        "status": "ok",
        "application": "URBANFLOW",
    }


# ============================================================
# REFERENCE SOURCES
# ============================================================

@router.get("/reference-sources")
def reference_sources():

    return [
        "Sentinel-2",
        "Google Earth Pro",
        "Other",
    ]


# ============================================================
# LOAD PROJECT
# ============================================================

@router.post("/project/load")
async def load_project(

    study_area: str = Form(...),
    year: str = Form(...),

    lulc_file: UploadFile = File(...),
    reference_file: UploadFile = File(...),
    points_file: UploadFile = File(...),

):

    try:

        session_dir = (
            PROJECT_DATA
            / "current"
        )

        session_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        lulc_path = (
            session_dir
            / lulc_file.filename
        )

        reference_path = (
            session_dir
            / reference_file.filename
        )

        points_path = (
            session_dir
            / points_file.filename
        )

        with lulc_path.open(
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                lulc_file.file,
                buffer
            )

        with reference_path.open(
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                reference_file.file,
                buffer
            )

        with points_path.open(
            "wb"
        ) as buffer:

            shutil.copyfileobj(
                points_file.file,
                buffer
            )

        df = pd.read_csv(
            points_path
        )

        df = prepare_points(
            df
        )

        state.area = study_area

        state.year = str(
            year
        )

        # IMPORTANT:
        # Restore any existing validations from PostgreSQL.
        df = _apply_database_validations(
            df
        )

        state.lulc_path = lulc_path
        state.reference_path = reference_path
        state.points_path = points_path
        state.points = df

        state.raster.set_paths(
            str(lulc_path),
            str(reference_path)
        )

        PROJECT_STATE_FILE.write_text(
            json.dumps(
                {
                    "area": state.area,
                    "year": state.year,
                    "lulc_file": lulc_path.name,
                    "reference_file": reference_path.name,
                    "points_file": points_path.name,
                },
                indent=2
            ),
            encoding="utf-8",
        )

        return {
            "status": "success",
            "area": state.area,
            "year": state.year,
            "total_points": len(df),
            "lulc_file": lulc_path.name,
            "reference_file": reference_path.name,
            "points_file": points_path.name,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# PROJECT INFO
# ============================================================

@router.get("/project/info")
def project_info():

    _restore_project_if_possible()

    return {

        "project_name": "URBANFLOW",

        "study_area": state.area,

        "year": state.year,

        "lulc_loaded": (
            state.lulc_path is not None
        ),

        "reference_loaded": (
            state.reference_path is not None
        ),

        "points_loaded": (
            not state.points.empty
        ),

        "total_points": len(
            state.points
        ),

        "validated_points": len(
            _validated_indices()
        ),
    }


# ============================================================
# GET ALL POINTS
# ============================================================

@router.get("/points")
def get_points():

    _restore_project_if_possible()

    if state.points.empty:

        raise HTTPException(
            status_code=400,
            detail="No validation points are loaded.",
        )

    records = []

    validated_indices = _validated_indices()

    for index, row in state.points.iterrows():

        dw = row.get(
            "DW_Class"
        )

        ref = row.get(
            "Reference_Class"
        )

        records.append(

            {
                "index": int(index),

                "longitude": float(
                    row["Longitude"]
                ),

                "latitude": float(
                    row["Latitude"]
                ),

                "dw_class": (
                    int(dw)
                    if pd.notna(dw)
                    else None
                ),

                "dw_class_name": (
                    _class_name(dw)
                    if pd.notna(dw)
                    else None
                ),

                "reference_class": (
                    int(ref)
                    if pd.notna(ref)
                    else None
                ),

                "reference_class_name": (
                    _class_name(ref)
                    if pd.notna(ref)
                    else None
                ),

                "reference_source": (

                    str(
                        row.get(
                            "Reference_Source",
                            ""
                        )
                    )

                    if pd.notna(
                        row.get(
                            "Reference_Source",
                            ""
                        )
                    )

                    else ""
                ),

                "validated": (
                    int(index)
                    in validated_indices
                ),

                "validation_status": (

                    "Validated"

                    if (
                        int(index)
                        in validated_indices
                    )

                    else "Not validated"
                ),
            }
        )

    return records


# ============================================================
# GET SINGLE POINT
# ============================================================

@router.get("/points/{index}")
def get_point(index: int):

    points = get_points()

    if (
        index < 0
        or index >= len(points)
    ):

        raise HTTPException(
            status_code=404,
            detail="Point not found.",
        )

    return points[index]


# ============================================================
# UPDATE REFERENCE
# ============================================================

@router.put(
    "/points/{index}/reference"
)
def update_reference(

    index: int,

    update: ReferenceUpdate,

):

    if state.points.empty:

        raise HTTPException(
            status_code=400,
            detail="No validation points loaded.",
        )

    if index not in state.points.index:

        raise HTTPException(
            status_code=404,
            detail="Point not found.",
        )

    if not (
        0
        <= update.reference_class
        <= 8
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Reference class must be "
                "between 0 and 8."
            ),
        )

    state.points = update_reference_class(
        state.points,
        index,
        update.reference_class,
        update.reference_source,
    )

    state.points.to_csv(
        state.points_path,
        index=False
    )

    return {

        "status": "success",

        "index": index,

        "reference_class": (
            update.reference_class
        ),

        "reference_source": (
            update.reference_source
        ),
    }


# ============================================================
# VALIDATE POINT
# ============================================================

@router.post(
    "/points/{index}/validate"
)
def validate_point(

    index: int,

    request: ValidationRequest,

    current_user=Depends(
        get_current_user
    ),

):

    """
    Save validation permanently in PostgreSQL.

    Each validation is associated with:
    - area
    - year
    - point
    - reference class
    - reference source
    - user who validated it
    """

    _restore_project_if_possible()

    if state.points.empty:

        raise HTTPException(
            status_code=400,
            detail="No validation points loaded.",
        )

    if index not in state.points.index:

        raise HTTPException(
            status_code=404,
            detail=f"Point {index + 1} not found.",
        )

    if not 0 <= int(
        request.reference_class
    ) <= 8:

        raise HTTPException(
            status_code=400,
            detail=(
                "Reference class must be "
                "between 0 and 8."
            ),
        )

    source = str(
        request.reference_source or ""
    ).strip()

    if not source:

        raise HTTPException(
            status_code=400,
            detail=(
                "A Reference Source is required "
                "before validation."
            ),
        )

    # --------------------------------------------------------
    # Get logged-in user
    # --------------------------------------------------------

    if isinstance(
        current_user,
        dict
    ):

        user_id = int(
            current_user["id"]
        )

    else:

        user_id = int(
            current_user.id
        )

    # --------------------------------------------------------
    # Save validation in PostgreSQL
    # --------------------------------------------------------

    db = SessionLocal()

    try:

        existing = (

            db.query(
                ValidationRecord
            )

            .filter(

                ValidationRecord.area
                == state.area,

                ValidationRecord.year
                == int(state.year),

                ValidationRecord.point_id
                == int(index),

            )

            .first()
        )

        if existing:

            # Save previous state in history
            history = ValidationHistory(

                area=existing.area,

                year=existing.year,

                point_id=existing.point_id,

                reference_class=(
                    existing.reference_class
                ),

                reference_source=(
                    existing.reference_source
                ),

                changed_by=(
                    existing.validated_by
                ),

            )

            db.add(
                history
            )

            # Update existing validation
            existing.reference_class = int(
                request.reference_class
            )

            existing.reference_source = source

            existing.validated_by = user_id

        else:

            record = ValidationRecord(

                area=state.area,

                year=int(state.year),

                point_id=int(index),

                reference_class=int(
                    request.reference_class
                ),

                reference_source=source,

                validated_by=user_id,

            )

            db.add(
                record
            )

        db.commit()

    except Exception as exc:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=(
                f"Database validation error: {exc}"
            ),
        )

    finally:

        db.close()

    # --------------------------------------------------------
    # Keep current project state updated
    # --------------------------------------------------------

    state.points = update_reference_class(
        state.points,
        index,
        int(
            request.reference_class
        ),
        source,
    )

    return {

        "status": "success",

        "validated": True,

        "validation_status": "Validated",

        "index": int(index),

        "reference_class": int(
            request.reference_class
        ),

        "reference_source": source,

        "validated_by": user_id,

    }


# ============================================================
# RASTER WINDOW
# ============================================================

@router.get(
    "/raster/window"
)
def raster_window(

    kind: str,

    longitude: float,

    latitude: float,

    radius_pixels: int = 100,

):

    if state.lulc_path is None:

        raise HTTPException(
            status_code=400,
            detail=(
                "Project has not been loaded."
            ),
        )

    try:

        if kind == "lulc":

            result = (
                state.raster
                .read_lulc_window(
                    longitude,
                    latitude,
                    radius_pixels,
                )
            )

        elif kind == "reference":

            result = (
                state.raster
                .read_reference_window(
                    longitude,
                    latitude,
                    radius_pixels,
                )
            )

        else:

            raise HTTPException(
                status_code=400,
                detail=(
                    "kind must be "
                    "lulc or reference."
                ),
            )

        data = result["data"]

        return {

            "data": data.tolist(),

            "row": result["row"],

            "column": result["column"],

            "window": result["window"],

            "crs": result["crs"],

            "transform": result["transform"],

        }

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# GOOGLE EARTH
# ============================================================

@router.post(
    "/points/{index}/google-earth"
)
def google_earth(index: int):

    if state.points.empty:

        raise HTTPException(
            status_code=400,
            detail="No points loaded.",
        )

    if index not in state.points.index:

        raise HTTPException(
            status_code=404,
            detail="Point not found.",
        )

    row = state.points.loc[
        index
    ]

    dw = row.get(
        "DW_Class"
    )

    ref = row.get(
        "Reference_Class"
    )

    try:

        return GoogleEarthService.open_point(

            float(
                row["Longitude"]
            ),

            float(
                row["Latitude"]
            ),

            int(index),

            (
                _class_name(dw)
                if pd.notna(dw)
                else None
            ),

            (
                _class_name(ref)
                if pd.notna(ref)
                else None
            ),

        )

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# VALIDATION RESULTS
# ============================================================

@router.get(
    "/validation/results"
)
def validation_results():

    if state.points.empty:

        raise HTTPException(
            status_code=400,
            detail=(
                "No validation points are loaded."
            ),
        )

    try:

        # ----------------------------------------------------
        # Get validated point IDs from PostgreSQL
        # ----------------------------------------------------

        validated = _validated_indices()

        # ----------------------------------------------------
        # CRITICAL:
        # Refresh reference classes directly from PostgreSQL
        # before calculating metrics.
        # ----------------------------------------------------

        current_points = (
            state.points.copy()
        )

        current_points = (
            _apply_database_validations(
                current_points
            )
        )

        # ----------------------------------------------------
        # Keep ONLY explicitly validated points
        # ----------------------------------------------------

        validated_df = (
            current_points.loc[
                current_points.index.isin(
                    validated
                )
            ].copy()
        )

        if validated_df.empty:

            return {

                "total_samples": 0,

                "correct_samples": 0,

                "overall_accuracy": 0,

                "kappa": 0,

                "confusion_matrix": [
                    [0] * 9
                    for _ in range(9)
                ],

                "class_metrics": [],

            }

        # ----------------------------------------------------
        # Calculate metrics using the refreshed dataframe
        # ----------------------------------------------------

        result = calculate_metrics(
            validated_df
        )

        class_metrics = []

        for item in result[
            "class_metrics"
        ].to_dict("records"):

            class_metrics.append(

                {

                    "class_id": item[
                        "Class_ID"
                    ],

                    "class_name": item[
                        "Class_Name"
                    ],

                    "reference_total": item[
                        "Reference_Total"
                    ],

                    "dw_total": item[
                        "DW_Total"
                    ],

                    "correct": item[
                        "Correct"
                    ],

                    "producer_accuracy": item[
                        "Producer_Accuracy"
                    ],

                    "user_accuracy": item[
                        "User_Accuracy"
                    ],

                }

            )

        return {

            "total_samples": result[
                "total_samples"
            ],

            "correct_samples": result[
                "correct_samples"
            ],

            "overall_accuracy": result[
                "overall_accuracy"
            ],

            "kappa": result[
                "kappa"
            ],

            "confusion_matrix": (
                result[
                    "confusion_matrix"
                ]
                .values
                .tolist()
            ),

            "class_metrics": class_metrics,

        }

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# VALIDATION EXPORT
# ============================================================

@router.post(
    "/validation/export"
)
def export_validation():

    if state.points.empty:

        raise HTTPException(
            status_code=400,
            detail=(
                "No validation points loaded."
            ),
        )

    try:

        # ----------------------------------------------------
        # Get validated point IDs from PostgreSQL
        # ----------------------------------------------------

        validated = (
            _validated_indices()
        )

        # ----------------------------------------------------
        # Refresh reference labels from PostgreSQL
        # ----------------------------------------------------

        current_points = (
            state.points.copy()
        )

        current_points = (
            _apply_database_validations(
                current_points
            )
        )

        # ----------------------------------------------------
        # Keep ONLY explicitly validated points
        # ----------------------------------------------------

        validated_df = (
            current_points.loc[
                current_points.index.isin(
                    validated
                )
            ].copy()
        )

        if validated_df.empty:

            raise HTTPException(
                status_code=400,
                detail=(
                    "No explicitly validated "
                    "points to export."
                ),
            )

        # ----------------------------------------------------
        # Calculate metrics
        # ----------------------------------------------------

        result = calculate_metrics(
            validated_df
        )

        session_name = (
            f"{state.area}_{state.year}"
        )

        session_dir = (
            OUTPUT_DIR
            / session_name
        )

        session_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        validated_csv = (
            session_dir
            / f"validation_{state.year}.csv"
        )

        confusion_csv = (
            session_dir
            / f"confusion_matrix_{state.year}.csv"
        )

        class_accuracy_csv = (
            session_dir
            / f"class_accuracy_metrics_{state.year}.csv"
        )

        overall_csv = (
            session_dir
            / f"overall_accuracy_kappa_{state.year}.csv"
        )

        validated_df.to_csv(
            validated_csv,
            index=False
        )

        result[
            "confusion_matrix"
        ].to_csv(
            confusion_csv
        )

        result[
            "class_metrics"
        ].to_csv(
            class_accuracy_csv,
            index=False
        )

        pd.DataFrame(
            [
                {
                    "Overall_Accuracy":
                        result[
                            "overall_accuracy"
                        ],

                    "Kappa":
                        result["kappa"],

                    "Total_Validated":
                        result[
                            "total_samples"
                        ],

                    "Correct":
                        result[
                            "correct_samples"
                        ],

                }
            ]
        ).to_csv(
            overall_csv,
            index=False
        )

        history_record = (
            save_history_record(

                state.area,

                state.year,

                len(
                    state.points
                ),

                result[
                    "total_samples"
                ],

                result[
                    "overall_accuracy"
                ],

                result[
                    "kappa"
                ],

            )
        )

        return {

            "status": "success",

            "message":
                "Validation results exported successfully.",

            "output_directory":
                str(session_dir),

            "files": [

                validated_csv.name,

                confusion_csv.name,

                class_accuracy_csv.name,

                overall_csv.name,

            ],

            "history":
                history_record,

        }

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# HISTORY
# ============================================================

@router.get(
    "/history"
)
def history():

    return load_history()


# ============================================================
# CLASS NAME
# ============================================================

def _class_name(value):

    names = {

        0: "Water",

        1: "Trees",

        2: "Grass",

        3: "Flooded Vegetation",

        4: "Crops",

        5: "Shrub/Scrub",

        6: "Built-up",

        7: "Bare Land",

        8: "Snow/Ice",

    }

    try:

        return names[
            int(value)
        ]

    except Exception:

        return None