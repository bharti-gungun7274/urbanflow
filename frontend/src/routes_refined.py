from pathlib import Path
import shutil

import pandas as pd
from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
)
from pydantic import BaseModel

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
from backend.services.validation_session_service import (
    load_session,
    save_point as save_session_point,
)


router = APIRouter(
    prefix="/api"
)


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


class ReferenceUpdate(BaseModel):
    reference_class: int
    reference_source: str = ""


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

PROJECT_STATE_FILE = PROJECT_DATA / "current" / "project_state.json"

def _session():
    if not state.area or not state.year:
        return {"validated_points": {}}
    return load_session(state.area, int(state.year))

def _validated_indices():
    session = _session()
    return {int(key) for key in session.get("validated_points", {}).keys()}


def _apply_saved_validation_session(df: pd.DataFrame) -> pd.DataFrame:
    """Restore saved reference labels/sources from the persistent validation session.

    This is what makes validation survive browser navigation, frontend refreshes,
    backend restarts, and reopening the same project files later.
    """
    if df.empty or not state.area or not state.year:
        return df

    session = load_session(state.area, int(state.year))
    saved_points = session.get("validated_points", {})

    if not isinstance(saved_points, dict):
        return df

    for key, saved in saved_points.items():
        try:
            point_id = int(key)
            if point_id not in df.index or not isinstance(saved, dict):
                continue

            if "reference_class" in saved:
                df.at[point_id, "Reference_Class"] = int(
                    saved["reference_class"]
                )

            if "reference_source" in saved:
                df.at[point_id, "Reference_Source"] = str(
                    saved.get("reference_source", "")
                )
        except (TypeError, ValueError):
            continue

    return df

def _restore_project_if_possible():
    if not PROJECT_STATE_FILE.exists() or not state.points.empty:
        return
    try:
        import json
        data = json.loads(PROJECT_STATE_FILE.read_text(encoding="utf-8"))
        current = PROJECT_DATA / "current"
        lulc = current / data["lulc_file"]
        reference = current / data["reference_file"]
        points = current / data["points_file"]
        if not (lulc.exists() and reference.exists() and points.exists()):
            return
        df = prepare_points(pd.read_csv(points))
        state.area = str(data["area"])
        state.year = str(data["year"])
        df = _apply_saved_validation_session(df)
        state.lulc_path = lulc
        state.reference_path = reference
        state.points_path = points
        state.points = df
        state.raster.set_paths(str(lulc), str(reference))
    except Exception:
        return


@router.get("/health")
def health():
    return {
        "status": "ok",
        "application": "URBANFLOW",
    }


@router.get("/reference-sources")
def reference_sources():
    return [
        "Sentinel-2",
        "Google Earth Pro",
        "Other",
    ]


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

        with lulc_path.open("wb") as buffer:
            shutil.copyfileobj(
                lulc_file.file,
                buffer
            )

        with reference_path.open("wb") as buffer:
            shutil.copyfileobj(
                reference_file.file,
                buffer
            )

        with points_path.open("wb") as buffer:
            shutil.copyfileobj(
                points_file.file,
                buffer
            )

        df = pd.read_csv(
            points_path
        )

        df = prepare_points(df)

        state.area = study_area
        state.year = str(year)
        df = _apply_saved_validation_session(df)

        state.lulc_path = lulc_path
        state.reference_path = reference_path
        state.points_path = points_path
        state.points = df

        state.raster.set_paths(
            str(lulc_path),
            str(reference_path)
        )

        import json
        PROJECT_STATE_FILE.write_text(
            json.dumps({
                "area": state.area,
                "year": state.year,
                "lulc_file": lulc_path.name,
                "reference_file": reference_path.name,
                "points_file": points_path.name,
            }, indent=2),
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


@router.get("/project/info")
def project_info():
    _restore_project_if_possible()
    return {
        "project_name": "URBANFLOW",
        "study_area": state.area,
        "year": state.year,
        "lulc_loaded": state.lulc_path is not None,
        "reference_loaded": (
            state.reference_path is not None
        ),
        "points_loaded": not state.points.empty,
        "total_points": len(state.points),
        "validated_points": len(_validated_indices()),
    }


@router.get("/points")
def get_points():
    _restore_project_if_possible()
    if state.points.empty:
        raise HTTPException(
            status_code=400,
            detail="No validation points are loaded.",
        )

    records = []

    for index, row in state.points.iterrows():
        dw = row.get("DW_Class")
        ref = row.get("Reference_Class")

        records.append({
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
            "validated": int(index) in _validated_indices(),
            "validation_status": (
                "Validated"
                if int(index) in _validated_indices()
                else "Not validated"
            ),
        })

    return records


@router.get("/points/{index}")
def get_point(index: int):
    points = get_points()

    if index < 0 or index >= len(points):
        raise HTTPException(
            status_code=404,
            detail="Point not found.",
        )

    return points[index]


@router.put("/points/{index}/reference")
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

    if not 0 <= update.reference_class <= 8:
        raise HTTPException(
            status_code=400,
            detail="Reference class must be between 0 and 8.",
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
        "reference_class": update.reference_class,
        "reference_source": update.reference_source,
    }


@router.post("/points/{index}/validate")
def validate_point(index: int):
    _restore_project_if_possible()
    if state.points.empty:
        raise HTTPException(status_code=400, detail="No validation points loaded.")
    if index not in state.points.index:
        raise HTTPException(status_code=404, detail="Point not found.")

    row = state.points.loc[index]
    ref = row.get("Reference_Class")
    source = row.get("Reference_Source", "")
    if pd.isna(ref) or not 0 <= int(ref) <= 8:
        raise HTTPException(status_code=400, detail="A valid Reference Class is required before validation.")
    if pd.isna(source) or not str(source).strip():
        raise HTTPException(status_code=400, detail="A Reference Source is required before validation.")

    result = save_session_point(
        state.area,
        int(state.year),
        int(index),
        int(ref),
        str(source),
    )
    return {
        "status": "success",
        "validated": True,
        "index": int(index),
        "reference_class": int(ref),
        "reference_source": str(source),
        "session_file": result.get("session_file"),
    }


@router.get("/raster/window")
def raster_window(
    kind: str,
    longitude: float,
    latitude: float,
    radius_pixels: int = 100,
):
    if state.lulc_path is None:
        raise HTTPException(
            status_code=400,
            detail="Project has not been loaded.",
        )

    try:
        if kind == "lulc":
            result = (
                state.raster.read_lulc_window(
                    longitude,
                    latitude,
                    radius_pixels,
                )
            )

        elif kind == "reference":
            result = (
                state.raster.read_reference_window(
                    longitude,
                    latitude,
                    radius_pixels,
                )
            )

        else:
            raise HTTPException(
                status_code=400,
                detail="kind must be lulc or reference.",
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

    row = state.points.loc[index]

    dw = row.get("DW_Class")
    ref = row.get("Reference_Class")

    try:
        return GoogleEarthService.open_point(
            float(row["Longitude"]),
            float(row["Latitude"]),
            int(index),
            _class_name(dw)
            if pd.notna(dw)
            else None,
            _class_name(ref)
            if pd.notna(ref)
            else None,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.get("/validation/results")
def validation_results():
    if state.points.empty:
        raise HTTPException(
            status_code=400,
            detail="No validation points are loaded.",
        )

    try:
        validated = _validated_indices()
        validated_df = state.points.loc[state.points.index.isin(validated)].copy()
        if validated_df.empty:
            return {
                "total_samples": 0,
                "correct_samples": 0,
                "overall_accuracy": 0,
                "kappa": 0,
                "confusion_matrix": [[0] * 9 for _ in range(9)],
                "class_metrics": [],
            }
        result = calculate_metrics(validated_df)

        class_metrics = []

        for item in result[
            "class_metrics"
        ].to_dict("records"):
            class_metrics.append({
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
            })

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
            "kappa": result["kappa"],
            "confusion_matrix":
                result[
                    "confusion_matrix"
                ].values.tolist(),
            "class_metrics": class_metrics,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.post("/validation/export")
def export_validation():
    if state.points.empty:
        raise HTTPException(
            status_code=400,
            detail="No validation points loaded.",
        )

    try:
        validated = _validated_indices()
        validated_df = state.points.loc[state.points.index.isin(validated)].copy()
        if validated_df.empty:
            raise HTTPException(status_code=400, detail="No explicitly validated points to export.")

        result = calculate_metrics(validated_df)

        session_name = (
            f"{state.area}_{state.year}"
        )

        session_dir = (
            OUTPUT_DIR / session_name
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

        pd.DataFrame([{
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
        }]).to_csv(
            overall_csv,
            index=False
        )

        history_record = (
            save_history_record(
                state.area,
                state.year,
                len(state.points),
                result[
                    "total_samples"
                ],
                result[
                    "overall_accuracy"
                ],
                result["kappa"],
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
            "history": history_record,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


@router.get("/history")
def history():
    return load_history()


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
        return names[int(value)]
    except Exception:
        return None
