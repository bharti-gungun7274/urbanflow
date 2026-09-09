from pathlib import Path
import shutil
import json
import zipfile
from datetime import datetime, timedelta

import pandas as pd

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    Depends,
    Query,
)

from fastapi.responses import FileResponse

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


# ============================================================
# USER-SCOPED REQUEST STATE
# ============================================================

from contextvars import ContextVar

_CURRENT_USER_ID = ContextVar("urbanflow_current_user_id", default=None)
_USER_PROJECT_STATES = {}


def _get_user_id(current_user):
    if isinstance(current_user, dict):
        return int(current_user["id"])
    return int(current_user.id)


async def _bind_current_user(current_user=Depends(get_current_user)):
    token = _CURRENT_USER_ID.set(_get_user_id(current_user))
    try:
        yield current_user
    finally:
        _CURRENT_USER_ID.reset(token)


class _UserProjectStateProxy:
    def _get_state(self):
        user_id = _CURRENT_USER_ID.get()
        if user_id is None:
            raise RuntimeError("No authenticated user is bound to the request.")

        if user_id not in _USER_PROJECT_STATES:
            _USER_PROJECT_STATES[user_id] = ProjectState()

        return _USER_PROJECT_STATES[user_id]

    def __getattr__(self, name):
        return getattr(self._get_state(), name)

    def __setattr__(self, name, value):
        if name == "_internal":
            object.__setattr__(self, name, value)
        else:
            setattr(self._get_state(), name, value)


state = _UserProjectStateProxy()


# ============================================================
# API ROUTER
# ============================================================

router = APIRouter(
    prefix="/api",
    dependencies=[Depends(_bind_current_user)],
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
# ACTIVE USER SESSION TRACKING
# ============================================================

ACTIVE_USERS_FILE = OUTPUT_DIR / "active_users.json"

ACTIVE_USER_TIMEOUT_SECONDS = 60


def _load_active_users():
    if not ACTIVE_USERS_FILE.exists():
        return []

    try:
        data = json.loads(
            ACTIVE_USERS_FILE.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(data, list):
            return []

        return data

    except (json.JSONDecodeError, OSError):
        return []


def _save_active_users(users):
    ACTIVE_USERS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    ACTIVE_USERS_FILE.write_text(
        json.dumps(
            users,
            indent=2
        ),
        encoding="utf-8"
    )


def _cleanup_active_users():
    users = _load_active_users()

    now = datetime.now()

    active = []

    for user in users:

        try:

            last_seen = datetime.fromisoformat(
                user["last_seen"]
            )

            if (
                now - last_seen
            ).total_seconds() <= ACTIVE_USER_TIMEOUT_SECONDS:

                active.append(user)

        except Exception:

            continue

    if len(active) != len(users):
        _save_active_users(active)

    return active


def _register_active_user():
    user_id = _user_id()

    db = SessionLocal()

    try:

        from backend.models import User

        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        username = (
            user.username
            if user is not None
            else f"User {user_id}"
        )

    finally:

        db.close()

    users = _cleanup_active_users()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    found = False

    for item in users:

        if int(
            item.get(
                "user_id",
                -1
            )
        ) == user_id:

            item["username"] = username
            item["last_seen"] = now

            found = True

            break

    if not found:

        users.append(
            {
                "user_id": user_id,
                "username": username,
                "area": "",
                "year": "",
                "status": "Active",
                "last_seen": now,
            }
        )

    _save_active_users(users)


def _update_active_user_project(
    area,
    year
):

    user_id = _user_id()

    db = SessionLocal()

    try:

        from backend.models import User

        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        username = (
            user.username
            if user is not None
            else f"User {user_id}"
        )

    finally:

        db.close()

    users = _cleanup_active_users()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    found = False

    for item in users:

        if int(
            item.get(
                "user_id",
                -1
            )
        ) == user_id:

            item["username"] = username
            item["area"] = str(area)
            item["year"] = int(year)
            item["status"] = "Active"
            item["last_seen"] = now

            found = True

            break

    if not found:

        users.append(
            {
                "user_id": user_id,
                "username": username,
                "area": str(area),
                "year": int(year),
                "status": "Active",
                "last_seen": now,
            }
        )

    _save_active_users(users)


def _heartbeat_active_user():

    user_id = _user_id()

    users = _cleanup_active_users()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    for item in users:

        if int(
            item.get(
                "user_id",
                -1
            )
        ) == user_id:

            item["last_seen"] = now
            item["status"] = "Active"

            _save_active_users(users)

            return

    _register_active_user()


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


def _project_current_dir():

    user_id = _CURRENT_USER_ID.get()

    if user_id is None:
        raise RuntimeError(
            "No authenticated user is bound to the request."
        )

    path = (
        PROJECT_DATA
        / "users"
        / str(user_id)
        / "current"
    )

    path.mkdir(
        parents=True,
        exist_ok=True
    )

    return path


def _project_state_file():
    return (
        _project_current_dir()
        / "project_state.json"
    )


# ============================================================
# USER-SCOPED SESSION / HISTORY HELPERS
# ============================================================

def _user_id():

    user_id = _CURRENT_USER_ID.get()

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Authenticated user is required.",
        )

    return int(user_id)


def _session_dir(
    area: str,
    year: int
):

    path = (
        PROJECT_DATA
        / "users"
        / str(_user_id())
        / "sessions"
        / f"{area}_{int(year)}"
    )

    path.mkdir(
        parents=True,
        exist_ok=True
    )

    return path


def _session_state_file(
    area: str,
    year: int
):

    return (
        _session_dir(area, year)
        / "project_state.json"
    )


def _history_file():

    path = (
        OUTPUT_DIR
        / "history"
        / f"user_{_user_id()}_history.json"
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    return path


def _load_user_history():

    path = _history_file()

    if not path.exists():
        return []

    try:

        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        return (
            data
            if isinstance(data, list)
            else []
        )

    except (
        json.JSONDecodeError,
        OSError
    ):

        return []


def _save_user_history_record(
    area,
    year,
    total_points,
    validated_points,
    overall_accuracy,
    kappa,
):

    history = _load_user_history()

    history.insert(
        0,
        {
            "area": str(area),
            "year": int(year),
            "total_points": int(total_points),
            "validated_points": int(validated_points),
            "overall_accuracy": float(overall_accuracy),
            "kappa": float(kappa),
            "timestamp": datetime.now().isoformat(
                timespec="seconds"
            ),
            "user_id": _user_id(),
        },
    )

    _history_file().write_text(
        json.dumps(
            history,
            indent=2
        ),
        encoding="utf-8",
    )

    return history[0]


def _validate_area_year(
    area,
    year
):

    allowed_areas = {
        "Delhi",
        "Mathura",
        "Agra"
    }

    allowed_years = {
        2018,
        2020,
        2022,
        2024
    }

    if area not in allowed_areas:

        raise HTTPException(
            status_code=400,
            detail=(
                "Area must be Delhi, Mathura or Agra."
            ),
        )

    try:

        year = int(year)

    except (
        TypeError,
        ValueError
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                "Year must be 2018, 2020, 2022 or 2024."
            ),
        )

    if year not in allowed_years:

        raise HTTPException(
            status_code=400,
            detail=(
                "Year must be 2018, 2020, 2022 or 2024."
            ),
        )

    return area, year


def _find_archived_project(
    area,
    year
):

    area, year = _validate_area_year(
        area,
        year
    )

    session_dir = _session_dir(
        area,
        year
    )

    state_file = (
        session_dir
        / "project_state.json"
    )

    if state_file.exists():

        try:

            data = json.loads(
                state_file.read_text(
                    encoding="utf-8"
                )
            )

            lulc = (
                session_dir
                / data["lulc_file"]
            )

            reference = (
                session_dir
                / data["reference_file"]
            )

            points = (
                session_dir
                / data["points_file"]
            )

            if (
                points.exists()
                and lulc.exists()
                and reference.exists()
            ):

                return {
                    "dir": session_dir,
                    "state": data,
                    "lulc": lulc,
                    "reference": reference,
                    "points": points,
                }

        except (
            KeyError,
            OSError,
            json.JSONDecodeError
        ):

            pass

    if (
        state.area == area
        and str(state.year) == str(year)
        and state.points_path is not None
        and state.lulc_path is not None
        and state.reference_path is not None
        and Path(state.points_path).exists()
        and Path(state.lulc_path).exists()
        and Path(state.reference_path).exists()
    ):

        return {
            "dir": _project_current_dir(),
            "state": {
                "area": area,
                "year": str(year),
                "lulc_file": Path(
                    state.lulc_path
                ).name,
                "reference_file": Path(
                    state.reference_path
                ).name,
                "points_file": Path(
                    state.points_path
                ).name,
            },
            "lulc": Path(
                state.lulc_path
            ),
            "reference": Path(
                state.reference_path
            ),
            "points": Path(
                state.points_path
            ),
        }

    output_dir = (
        OUTPUT_DIR
        / f"{area}_{year}"
    )

    exported_points = (
        output_dir
        / f"validation_{year}.csv"
    )

    if exported_points.exists():

        return {
            "dir": output_dir,
            "state": {
                "area": area,
                "year": str(year),
                "lulc_file": "",
                "reference_file": "",
                "points_file": exported_points.name,
            },
            "lulc": None,
            "reference": None,
            "points": exported_points,
        }

    raise HTTPException(
        status_code=404,
        detail=(
            f"No project data is available for {area} {year}. "
            "Load that Area/Year project once from the Validation page "
            "before viewing or exporting it."
        ),
    )


def _load_session_points(
    area,
    year
):

    project = _find_archived_project(
        area,
        year
    )

    df = prepare_points(
        pd.read_csv(
            project["points"]
        )
    )

    db = SessionLocal()

    try:

        records = (
            db.query(
                ValidationRecord
            )
            .filter(
                ValidationRecord.area == area,
                ValidationRecord.year == int(year),
                ValidationRecord.validated_by == _user_id(),
            )
            .all()
        )

    finally:

        db.close()

    validation_map = {
        int(record.point_id): record
        for record in records
    }

    if "Point_ID" in df.columns:

        ids = pd.to_numeric(
            df["Point_ID"],
            errors="coerce"
        )

        df["_Point_ID"] = ids

    else:

        df["_Point_ID"] = (
            df.index.astype(int)
        )

    for point_id, record in validation_map.items():

        matches = df.index[
            df["_Point_ID"] == point_id
        ].tolist()

        if (
            not matches
            and point_id in df.index
        ):

            matches = [point_id]

        for idx in matches:

            df.at[
                idx,
                "Reference_Class"
            ] = int(
                record.reference_class
            )

            df.at[
                idx,
                "Reference_Source"
            ] = str(
                record.reference_source
            )

    return (
        df,
        validation_map,
        project
    )


def _validated_session_dataframe(
    area,
    year
):

    (
        df,
        validation_map,
        project
    ) = _load_session_points(
        area,
        year
    )

    if not validation_map:

        return (
            df.iloc[0:0].copy(),
            df,
            project
        )

    df = df.copy()

    df["_Point_ID"] = pd.to_numeric(
        df.get(
            "_Point_ID",
            df.index
        ),
        errors="coerce",
    )

    validated_ids = set(
        validation_map.keys()
    )

    validated_df = df[
        df["_Point_ID"].isin(
            validated_ids
        )
    ].copy()

    if (
        validated_df.empty
        and len(df.index)
    ):

        matching = [
            idx
            for idx in df.index
            if int(idx) in validated_ids
        ]

        validated_df = df.loc[
            matching
        ].copy()

    return (
        validated_df,
        df,
        project
    )


def _format_validated_points(df):

    output = df.copy()

    if "_Point_ID" in output.columns:

        output["Point_ID"] = (
            output["_Point_ID"]
            .astype("Int64")
        )

        output.drop(
            columns=["_Point_ID"],
            inplace=True
        )

    if "Point_ID" not in output.columns:

        output.insert(
            0,
            "Point_ID",
            output.index.astype(int),
        )

    if "Longitude" in output.columns:

        output["Longitude"] = pd.to_numeric(
            output["Longitude"],
            errors="coerce"
        )

    if "Latitude" in output.columns:

        output["Latitude"] = pd.to_numeric(
            output["Latitude"],
            errors="coerce"
        )

    if "DW_Class" in output.columns:

        output["DW_Class"] = pd.to_numeric(
            output["DW_Class"],
            errors="coerce"
        )

        output["DW_Class_Name"] = (
            output["DW_Class"]
            .apply(_class_name)
        )

    if "Reference_Class" in output.columns:

        output["Reference_Class"] = pd.to_numeric(
            output["Reference_Class"],
            errors="coerce"
        )

        output["Reference_Class_Name"] = (
            output["Reference_Class"]
            .apply(_class_name)
        )

    return output.reset_index(
        drop=True
    )


# ============================================================
# VALIDATION HELPERS
# ============================================================

def _validated_indices():

    if not state.area or not state.year:
        return set()

    user_id = _CURRENT_USER_ID.get()

    if user_id is None:
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
                ValidationRecord.validated_by == int(
                    user_id
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
                ValidationRecord.validated_by == int(
                    _CURRENT_USER_ID.get()
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
        not _project_state_file().exists()
        or not state.points.empty
    ):

        return

    try:

        data = json.loads(
            _project_state_file().read_text(
                encoding="utf-8"
            )
        )

        current = _project_current_dir()

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
# ACTIVE USERS
# ============================================================

@router.post("/active-users/heartbeat")
def active_users_heartbeat():

    _heartbeat_active_user()

    return {
        "status": "ok",
        "message": "Active user heartbeat updated.",
    }


@router.get("/active-users")
def get_active_users():

    users = _cleanup_active_users()

    result = []

    for item in users:

        area = item.get(
            "area",
            ""
        )

        year = item.get(
            "year",
            ""
        )

        if not area or not year:
            continue

        result.append(
            {
                "username": item.get(
                    "username",
                    ""
                ),
                "area": area,
                "year": int(year),
                "status": "Active",
            }
        )

    return result


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

        session_dir = _project_current_dir()

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

        # ----------------------------------------------------
        # ACTIVE USER TRACKING
        # ----------------------------------------------------

        _update_active_user_project(
            study_area,
            int(year)
        )

        _project_state_file().write_text(
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

        archived_dir = _session_dir(
            study_area,
            int(year),
        )

        for source in (
            lulc_path,
            reference_path,
            points_path,
        ):

            shutil.copy2(
                source,
                archived_dir / source.name,
            )

        (
            archived_dir
            / "project_state.json"
        ).write_text(
            json.dumps(
                {
                    "area": state.area,
                    "year": state.year,
                    "lulc_file": lulc_path.name,
                    "reference_file": reference_path.name,
                    "points_file": points_path.name,
                },
                indent=2,
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

                ValidationRecord.validated_by
                == int(user_id),
            )
            .first()
        )

        if existing:

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

            db.add(history)

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

            db.add(record)

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

@router.get("/validation/results")
def validation_results(
    area: str = Query(None),
    year: int = Query(None),
):

    if area is None:
        area = state.area

    if year is None:
        year = state.year

    if not area or not year:

        raise HTTPException(
            status_code=400,
            detail="Please select an Area and Year.",
        )

    area, year = _validate_area_year(
        area,
        year
    )

    try:

        (
            validated_df,
            all_points,
            project
        ) = _validated_session_dataframe(
            area,
            year
        )

        if validated_df.empty:

            return {
                "area": area,
                "year": year,
                "total_points": int(
                    len(all_points)
                ),
                "total_samples": 0,
                "correct_samples": 0,
                "overall_accuracy": 0,
                "kappa": 0,
                "confusion_matrix": [
                    [0] * 9
                    for _ in range(9)
                ],
                "class_metrics": [],
                "message": (
                    f"No validated points are available for "
                    f"{area} {year}."
                ),
            }

        result = calculate_metrics(
            validated_df
        )

        class_metrics = []

        for item in (
            result[
                "class_metrics"
            ]
            .to_dict("records")
        ):

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

            "area": area,

            "year": year,

            "total_points": int(
                len(all_points)
            ),

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

            "confusion_matrix": result[
                "confusion_matrix"
            ].values.tolist(),

            "class_metrics": class_metrics,
        }

    except HTTPException:

        raise

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# EXPORT HELPERS
# ============================================================

def _build_export_bundle(
    area,
    year
):

    (
        validated_df,
        all_points,
        project
    ) = _validated_session_dataframe(
        area,
        year
    )

    if validated_df.empty:

        raise HTTPException(
            status_code=400,
            detail=(
                f"No explicitly validated points to export "
                f"for {area} {year}."
            ),
        )

    result = calculate_metrics(
        validated_df
    )

    formatted_points = _format_validated_points(
        validated_df
    )

    export_dir = (
        OUTPUT_DIR
        / "exports"
        / str(_user_id())
        / f"{area}_{year}"
    )

    export_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    validated_csv = (
        export_dir
        / f"{area}_{year}_validated_points_{timestamp}.csv"
    )

    confusion_csv = (
        export_dir
        / f"{area}_{year}_confusion_matrix_{timestamp}.csv"
    )

    accuracy_csv = (
        export_dir
        / f"{area}_{year}_class_accuracy_{timestamp}.csv"
    )

    summary_csv = (
        export_dir
        / f"{area}_{year}_validation_summary_{timestamp}.csv"
    )

    formatted_points.to_csv(
        validated_csv,
        index=False,
    )

    result[
        "confusion_matrix"
    ].to_csv(
        confusion_csv,
        index=True,
    )

    result[
        "class_metrics"
    ].to_csv(
        accuracy_csv,
        index=False,
    )

    pd.DataFrame(
        [
            {
                "Area": area,
                "Year": year,
                "User_ID": _user_id(),
                "Total_Points": len(
                    all_points
                ),
                "Validated_Points": result[
                    "total_samples"
                ],
                "Correct_Samples": result[
                    "correct_samples"
                ],
                "Overall_Accuracy": result[
                    "overall_accuracy"
                ],
                "Kappa": result[
                    "kappa"
                ],
                "Exported_At": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }
        ]
    ).to_csv(
        summary_csv,
        index=False,
    )

    return {

        "export_dir": export_dir,

        "validated_csv": validated_csv,

        "confusion_csv": confusion_csv,

        "accuracy_csv": accuracy_csv,

        "summary_csv": summary_csv,

        "result": result,

        "total_points": len(
            all_points
        ),
    }


def _download_response(
    path: Path
):

    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="text/csv",
    )


# ============================================================
# INDIVIDUAL EXPORTS
# ============================================================

@router.get(
    "/validation/export/validated-points"
)
def export_validated_points(
    area: str = Query(...),
    year: int = Query(...),
):

    area, year = _validate_area_year(
        area,
        year
    )

    bundle = _build_export_bundle(
        area,
        year
    )

    return _download_response(
        bundle["validated_csv"]
    )


@router.get(
    "/validation/export/confusion-matrix"
)
def export_confusion_matrix(
    area: str = Query(...),
    year: int = Query(...),
):

    area, year = _validate_area_year(
        area,
        year
    )

    bundle = _build_export_bundle(
        area,
        year
    )

    return _download_response(
        bundle["confusion_csv"]
    )


@router.get(
    "/validation/export/class-accuracy"
)
def export_class_accuracy(
    area: str = Query(...),
    year: int = Query(...),
):

    area, year = _validate_area_year(
        area,
        year
    )

    bundle = _build_export_bundle(
        area,
        year
    )

    return _download_response(
        bundle["accuracy_csv"]
    )


@router.get(
    "/validation/export/summary"
)
def export_validation_summary(
    area: str = Query(...),
    year: int = Query(...),
):

    area, year = _validate_area_year(
        area,
        year
    )

    bundle = _build_export_bundle(
        area,
        year
    )

    return _download_response(
        bundle["summary_csv"]
    )


@router.get(
    "/validation/export/complete"
)
def export_complete_validation_package(
    area: str = Query(...),
    year: int = Query(...),
):

    area, year = _validate_area_year(
        area,
        year
    )

    bundle = _build_export_bundle(
        area,
        year
    )

    zip_timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    zip_path = (
        bundle["export_dir"]
        / (
            f"URBANFLOW_{area}_{year}_"
            f"complete_validation_package_{zip_timestamp}.zip"
        )
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:

        for key in (
            "validated_csv",
            "confusion_csv",
            "accuracy_csv",
            "summary_csv",
        ):

            archive.write(
                bundle[key],
                arcname=bundle[key].name,
            )

    _save_user_history_record(
        area,
        year,
        bundle["total_points"],
        bundle["result"]["total_samples"],
        bundle["result"]["overall_accuracy"],
        bundle["result"]["kappa"],
    )

    return FileResponse(
        path=str(zip_path),
        filename=zip_path.name,
        media_type="application/zip",
    )


# ============================================================
# LEGACY EXPORT ENDPOINT
# ============================================================

@router.post(
    "/validation/export"
)
def export_validation(
    area: str = Query(None),
    year: int = Query(None),
):

    if area is None:
        area = state.area

    if year is None:
        year = state.year

    area, year = _validate_area_year(
        area,
        year
    )

    try:

        bundle = _build_export_bundle(
            area,
            year,
        )

        history_record = _save_user_history_record(
            area,
            year,
            bundle["total_points"],
            bundle["result"]["total_samples"],
            bundle["result"]["overall_accuracy"],
            bundle["result"]["kappa"],
        )

        return {

            "status": "success",

            "message": (
                "Validation results exported successfully."
            ),

            "area": area,

            "year": year,

            "output_directory": str(
                bundle["export_dir"]
            ),

            "files": [

                bundle[
                    "validated_csv"
                ].name,

                bundle[
                    "confusion_csv"
                ].name,

                bundle[
                    "accuracy_csv"
                ].name,

                bundle[
                    "summary_csv"
                ].name,
            ],

            "history": history_record,
        }

    except HTTPException:

        raise

    except Exception as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )


# ============================================================
# HISTORY
# ============================================================

@router.get("/history")
def history():

    return _load_user_history()


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