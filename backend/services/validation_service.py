import numpy as np
import pandas as pd

from backend.services.validation_session_service import (
    load_session,
    save_point as save_session_point,
)


# =========================================================
# URBANFLOW CONSTANTS
# =========================================================

ALLOWED_AREAS = [
    "Delhi",
    "Mathura",
    "Agra",
]

ALLOWED_YEARS = [
    2018,
    2020,
    2022,
    2024,
]


CLASS_NAMES = {
    0: "Water",
    1: "Trees",
    2: "Grass",
    3: "Flooded vegetation",
    4: "Crops",
    5: "Shrub/Scrub",
    6: "Built-up",
    7: "Bare land",
    8: "Snow/Ice",
}


# =========================================================
# PREPARE VALIDATION POINT CSV
# =========================================================

def prepare_points(df):
    df = df.copy()

    # Normalize column names
    normalized = {}

    for col in df.columns:
        clean = str(col).strip().lower()

        if clean in ["longitude", "lon", "x"]:
            normalized[col] = "Longitude"

        elif clean in ["latitude", "lat", "y"]:
            normalized[col] = "Latitude"

        elif clean in ["dw_class", "dynamic_world", "dw"]:
            normalized[col] = "DW_Class"

        elif clean in ["reference_class", "reference", "ref_class"]:
            normalized[col] = "Reference_Class"

        elif clean in ["reference_source", "source"]:
            normalized[col] = "Reference_Source"

    # Rename columns
    df = df.rename(columns=normalized)

    # ---------------------------------------------------------
    # Remove duplicate columns created by CSVs containing both
    # Latitude/latitude and Longitude/longitude
    # ---------------------------------------------------------

    def keep_first_column(df, column_name):
        matches = [
            i for i, col in enumerate(df.columns)
            if col == column_name
        ]

        if len(matches) <= 1:
            return df

        # Keep the first occurrence only
        keep_indices = [
            i for i in range(len(df.columns))
            if not (df.columns[i] == column_name and i != matches[0])
        ]

        return df.iloc[:, keep_indices]

    df = keep_first_column(df, "Longitude")
    df = keep_first_column(df, "Latitude")
    df = keep_first_column(df, "DW_Class")
    df = keep_first_column(df, "Reference_Class")
    df = keep_first_column(df, "Reference_Source")

    # Required columns
    if "Longitude" not in df.columns:
        raise ValueError("Validation CSV must contain a Longitude column.")

    if "Latitude" not in df.columns:
        raise ValueError("Validation CSV must contain a Latitude column.")

    if "DW_Class" not in df.columns:
        raise ValueError("Validation CSV must contain a DW_Class column.")

    # Reference columns are optional initially
    if "Reference_Class" not in df.columns:
        df["Reference_Class"] = np.nan

    if "Reference_Source" not in df.columns:
        df["Reference_Source"] = ""

    # Convert numeric columns
    df["Longitude"] = pd.to_numeric(
        df["Longitude"],
        errors="coerce"
    )

    df["Latitude"] = pd.to_numeric(
        df["Latitude"],
        errors="coerce"
    )

    df["DW_Class"] = pd.to_numeric(
        df["DW_Class"],
        errors="coerce"
    )

    df["Reference_Class"] = pd.to_numeric(
        df["Reference_Class"],
        errors="coerce"
    )

    # Remove invalid coordinates
    df = df[
        df["Longitude"].notna() &
        df["Latitude"].notna()
    ].copy()

    # Reset index
    df = df.reset_index(drop=True)

    return df

    # -----------------------------------------------------
    # Reference class
    # -----------------------------------------------------

    if "Reference_Class" not in df.columns:

        df["Reference_Class"] = np.nan

    else:

        df["Reference_Class"] = pd.to_numeric(
            df["Reference_Class"],
            errors="coerce"
        )

    # -----------------------------------------------------
    # Reference source
    # -----------------------------------------------------

    if "Reference_Source" not in df.columns:

        df["Reference_Source"] = ""

    # -----------------------------------------------------
    # Remove invalid coordinates
    # -----------------------------------------------------

    df = df[
        df["Longitude"].notna()
        & df["Latitude"].notna()
    ].copy()

    df = df.reset_index(drop=True)

    return df


# =========================================================
# CLASS NAME
# =========================================================

def get_class_name(class_id):

    if class_id is None:
        return None

    try:
        class_id = int(class_id)
    except (ValueError, TypeError):
        return None

    return CLASS_NAMES.get(
        class_id,
        "Unknown"
    )


# =========================================================
# VALIDATION METRICS
# =========================================================

def calculate_metrics(df: pd.DataFrame):

    required = [
        "DW_Class",
        "Reference_Class"
    ]

    for column in required:

        if column not in df.columns:

            raise ValueError(
                f"Missing required column: {column}"
            )

    # -----------------------------------------------------
    # Only validated points
    # -----------------------------------------------------

    valid = df[
        df["DW_Class"].notna()
        & df["Reference_Class"].notna()
    ].copy()

    # -----------------------------------------------------
    # Valid class range
    # -----------------------------------------------------

    valid = valid[
        valid["DW_Class"].between(0, 8)
        & valid["Reference_Class"].between(0, 8)
    ]

    if len(valid) == 0:

        raise ValueError(
            "No validated points are available yet."
        )

    dw = valid["DW_Class"].astype(int)

    reference = valid[
        "Reference_Class"
    ].astype(int)

    # -----------------------------------------------------
    # Confusion matrix
    #
    # Rows    = Reference / Actual
    # Columns = Dynamic World / Predicted
    # -----------------------------------------------------

    confusion = np.zeros(
        (9, 9),
        dtype=int
    )

    for actual, predicted in zip(
        reference,
        dw
    ):

        confusion[
            actual,
            predicted
        ] += 1

    class_labels = [
        CLASS_NAMES[i]
        for i in range(9)
    ]

    confusion_df = pd.DataFrame(
        confusion,
        index=class_labels,
        columns=class_labels
    )

    # -----------------------------------------------------
    # Overall Accuracy
    # -----------------------------------------------------

    total = confusion.sum()

    correct = np.trace(
        confusion
    )

    overall_accuracy = (
        correct / total
        if total > 0
        else 0.0
    )

    # -----------------------------------------------------
    # Producer Accuracy
    # -----------------------------------------------------

    row_totals = confusion.sum(
        axis=1
    )

    producer_accuracy = np.divide(
        np.diag(confusion),
        row_totals,
        out=np.zeros(
            9,
            dtype=float
        ),
        where=row_totals != 0
    )

    # -----------------------------------------------------
    # User Accuracy
    # -----------------------------------------------------

    column_totals = confusion.sum(
        axis=0
    )

    user_accuracy = np.divide(
        np.diag(confusion),
        column_totals,
        out=np.zeros(
            9,
            dtype=float
        ),
        where=column_totals != 0
    )

    # -----------------------------------------------------
    # Kappa
    # -----------------------------------------------------

    observed_agreement = overall_accuracy

    if total > 0:

        expected_agreement = (
            np.sum(
                row_totals * column_totals
            )
            / (total * total)
        )

    else:

        expected_agreement = 0.0

    if expected_agreement == 1:

        kappa = 1.0

    else:

        kappa = (
            observed_agreement
            - expected_agreement
        ) / (
            1
            - expected_agreement
        )

    # -----------------------------------------------------
    # Class-level metrics
    # -----------------------------------------------------

    class_metrics = []

    for class_id in range(9):

        class_metrics.append({

            "Class_ID": class_id,

            "Class_Name":
                CLASS_NAMES[class_id],

            "Reference_Total":
                int(row_totals[class_id]),

            "DW_Total":
                int(column_totals[class_id]),

            "Correct":
                int(
                    confusion[
                        class_id,
                        class_id
                    ]
                ),

            "Producer_Accuracy":
                float(
                    producer_accuracy[
                        class_id
                    ]
                ),

            "User_Accuracy":
                float(
                    user_accuracy[
                        class_id
                    ]
                ),
        })

    metrics_df = pd.DataFrame(
        class_metrics
    )

    # -----------------------------------------------------
    # Return everything
    # -----------------------------------------------------

    return {

        "confusion_matrix":
            confusion_df,

        "class_metrics":
            metrics_df,

        "total_samples":
            int(total),

        "correct_samples":
            int(correct),

        "overall_accuracy":
            float(
                overall_accuracy
            ),

        "kappa":
            float(kappa),
    }


# =========================================================
# UPDATE REFERENCE CLASS
# =========================================================

def update_reference_class(
    df: pd.DataFrame,
    index: int,
    reference_class: int,
    reference_source: str = ""
):

    if index < 0 or index >= len(df):

        raise IndexError(
            "Validation point index is out of range."
        )

    if reference_class not in CLASS_NAMES:

        raise ValueError(
            "Reference class must be between 0 and 8."
        )

    df = df.copy()

    df.at[
        index,
        "Reference_Class"
    ] = reference_class

    df.at[
        index,
        "Reference_Source"
    ] = reference_source

    return df