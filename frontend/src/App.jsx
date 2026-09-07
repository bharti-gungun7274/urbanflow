import React, { useEffect, useState, useRef } from "react";
import "./App.css";
import Login from "./Login";

import {
  loadProject,
  getProjectInfo,
  getPoints,
  getRasterWindow,
  validatePoint,
  getValidationResults,
  exportValidation,
  getHistory,
} from "./api";

/* =========================================================
CONSTANTS
========================================================= */

const CLASSES = [
  { id: 0, name: "Water" },
  { id: 1, name: "Trees" },
  { id: 2, name: "Grass" },
  { id: 3, name: "Flooded Vegetation" },
  { id: 4, name: "Crops" },
  { id: 5, name: "Shrub/Scrub" },
  { id: 6, name: "Built-up" },
  { id: 7, name: "Bare Land" },
  { id: 8, name: "Snow/Ice" },
];

const YEARS = ["2018", "2020", "2022", "2024"];

function className(id) {
  const item = CLASSES.find((item) => item.id === Number(id));
  return item ? item.name : "Not assigned";
}

function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function isValidatedPoint(point) {
  return (
    point?.validated === true ||
    point?.validation_status === "Validated"
  );
}

/* =========================================================
RASTER CANVAS
========================================================= */

function RasterCanvas({
  raster,
  pointNumber = 1,
  type = "lulc",
}) {
  const canvasRef = React.useRef(null);

  React.useEffect(() => {
    if (!raster || !raster.data) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const data = raster.data;

    const isReference =
      type === "reference" &&
      Array.isArray(data) &&
      Array.isArray(data[0]) &&
      Array.isArray(data[0][0]);

    let width;
    let height;

    if (isReference) {
      height = Number(
        raster.height ??
          raster.window?.height ??
          data[0]?.length ??
          0
      );

      width = Number(
        raster.width ??
          raster.window?.width ??
          data[0]?.[0]?.length ??
          0
      );
    } else {
      height = Number(
        raster.height ??
          raster.window?.height ??
          data.length ??
          0
      );

      width = Number(
        raster.width ??
          raster.window?.width ??
          data[0]?.length ??
          0
      );
    }

    width = Math.floor(width);
    height = Math.floor(height);

    if (
      !Number.isFinite(width) ||
      !Number.isFinite(height) ||
      width <= 0 ||
      height <= 0
    ) {
      console.error("URBANFLOW: Invalid raster size", {
        width,
        height,
        raster,
      });
      return;
    }

    canvas.width = width;
    canvas.height = height;

    let imageData;

    try {
      imageData = ctx.createImageData(width, height);
    } catch (error) {
      console.error(
        "URBANFLOW: createImageData failed",
        error
      );
      return;
    }

    /* =====================================================
       LULC DISPLAY
       ===================================================== */

    if (!isReference) {
      const colors = {
        0: [0, 0, 255],
        1: [0, 128, 0],
        2: [144, 238, 144],
        3: [0, 191, 255],
        4: [255, 255, 0],
        5: [218, 165, 32],
        6: [255, 0, 0],
        7: [210, 180, 140],
        8: [255, 255, 255],
        255: [255, 255, 255],
      };

      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const pixel = (y * width + x) * 4;

          const value = Number(data[y]?.[x]);

          const classValue = Number.isFinite(value)
            ? value
            : 255;

          const rgb =
            colors[classValue] || [255, 255, 255];

          imageData.data[pixel] = rgb[0];
          imageData.data[pixel + 1] = rgb[1];
          imageData.data[pixel + 2] = rgb[2];

          imageData.data[pixel + 3] =
            classValue === 255 ? 0 : 255;
        }
      }
    }

    /* =====================================================
       SENTINEL-2 REFERENCE DISPLAY
       ===================================================== */

    else {
      const redBand = data[2] || [];
      const greenBand = data[1] || [];
      const blueBand = data[0] || [];

      const displayMaximum = 3000;

      const enhance = (value) => {
        const normalized =
          value / displayMaximum;

        const stretched = Math.pow(
          Math.max(
            0,
            Math.min(1, normalized)
          ),
          0.75
        );

        return Math.round(stretched * 255);
      };

      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const pixel = (y * width + x) * 4;

          const red = Number(
            redBand[y]?.[x] ?? 0
          );

          const green = Number(
            greenBand[y]?.[x] ?? 0
          );

          const blue = Number(
            blueBand[y]?.[x] ?? 0
          );

          imageData.data[pixel] =
            enhance(red);

          imageData.data[pixel + 1] =
            enhance(green);

          imageData.data[pixel + 2] =
            enhance(blue);

          imageData.data[pixel + 3] = 255;
        }
      }
    }

    ctx.putImageData(imageData, 0, 0);

    /* =====================================================
       POINT LOCATION
       ===================================================== */

    let pointX;
    let pointY;

    if (
      raster.point_column !== undefined &&
      raster.point_row !== undefined
    ) {
      pointX = Number(
        raster.point_column
      );

      pointY = Number(
        raster.point_row
      );
    } else if (
      raster.column !== undefined &&
      raster.row !== undefined &&
      raster.window
    ) {
      pointX =
        Number(raster.column) -
        Number(raster.window.col_off);

      pointY =
        Number(raster.row) -
        Number(raster.window.row_off);
    } else {
      pointX = Math.floor(width / 2);
      pointY = Math.floor(height / 2);
    }

    pointX = Math.max(
      0,
      Math.min(
        width - 1,
        Math.round(pointX)
      )
    );

    pointY = Math.max(
      0,
      Math.min(
        height - 1,
        Math.round(pointY)
      )
    );

    /* =====================================================
       CROSSHAIR
       ===================================================== */

    ctx.save();

    ctx.strokeStyle =
      "rgba(255,255,255,0.95)";

    ctx.lineWidth = 5;

    ctx.beginPath();

    ctx.moveTo(
      pointX - 18,
      pointY
    );

    ctx.lineTo(
      pointX + 18,
      pointY
    );

    ctx.moveTo(
      pointX,
      pointY - 18
    );

    ctx.lineTo(
      pointX,
      pointY + 18
    );

    ctx.stroke();

    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 2;

    ctx.beginPath();

    ctx.moveTo(
      pointX - 18,
      pointY
    );

    ctx.lineTo(
      pointX + 18,
      pointY
    );

    ctx.moveTo(
      pointX,
      pointY - 18
    );

    ctx.lineTo(
      pointX,
      pointY + 18
    );

    ctx.stroke();

    ctx.fillStyle = "#ffffff";

    ctx.beginPath();

    ctx.arc(
      pointX,
      pointY,
      4,
      0,
      Math.PI * 2
    );

    ctx.fill();

    ctx.strokeStyle = "#000000";
    ctx.lineWidth = 2;

    ctx.beginPath();

    ctx.arc(
      pointX,
      pointY,
      4,
      0,
      Math.PI * 2
    );

    ctx.stroke();

    ctx.restore();

  }, [raster, type, pointNumber]);

  if (!raster) {
    return (
      <div className="viewer-empty">
        No raster loaded
      </div>
    );
  }

  const width = Math.max(
    1,
    Number(
      raster.width ??
      raster.window?.width ??
      1
    )
  );

  const height = Math.max(
    1,
    Number(
      raster.height ??
      raster.window?.height ??
      1
    )
  );

  return (
    <div className="raster-viewer">
      <div
        className="raster-stage"
        style={{
          aspectRatio: `${width} / ${height}`,
        }}
      >
        <canvas
          ref={canvasRef}
          className="raster-canvas"
        />
      </div>
    </div>
  );
}

/* =========================================================
HEADER
========================================================= */

function Header({ page, setPage }) {
  return (
    <header className="header">
      <div className="brand">
        <div className="brand-mark">
          UF
        </div>

        <div className="brand-text">
          <div className="brand-title">
            URBANFLOW
          </div>

          <div className="brand-subtitle">
            YAMUNA URBANIZATION &amp; WATER QUALITY RESEARCH
          </div>
        </div>
      </div>

      <nav className="navigation">
        <button
          className={
            page === "validation"
              ? "nav-active"
              : ""
          }
          onClick={() =>
            setPage("validation")
          }
        >
          Validation
        </button>

        <button
          className={
            page === "results"
              ? "nav-active"
              : ""
          }
          onClick={() =>
            setPage("results")
          }
        >
          Results
        </button>

        <button
          className={
            page === "history"
              ? "nav-active"
              : ""
          }
          onClick={() =>
            setPage("history")
          }
        >
          History
        </button>
      </nav>
    </header>
  );
}

/* =========================================================
FILE SELECTOR
========================================================= */

function FileSelector({
  label,
  file,
  setFile,
  accept,
}) {
  const inputRef = useRef(null);

  function handleBrowse() {
    if (inputRef.current) {
      inputRef.current.value = "";
      inputRef.current.click();
    }
  }

  function handleFileChange(event) {
    const selectedFile =
      event.target.files &&
      event.target.files.length > 0
        ? event.target.files[0]
        : null;

    if (selectedFile) {
      console.log(
        "URBANFLOW selected file:",
        selectedFile.name,
        selectedFile.type,
        selectedFile.size
      );
    }

    setFile(selectedFile);
  }

  return (
    <div className="file-field">
      <label>{label}</label>

      <div className="file-row">
        <div className="file-name">
          {file
            ? file.name
            : "No file selected"}
        </div>

        <button
          type="button"
          className="browse-button"
          onClick={handleBrowse}
        >
          Browse
        </button>

        <input
          ref={inputRef}
          type="file"
          accept={
            label === "VALIDATION POINTS"
              ? ".csv,text/csv"
              : accept
          }
          onChange={handleFileChange}
          style={{ display: "none" }}
        />
      </div>
    </div>
  );
}

/* =========================================================
POINT DRAWER
========================================================= */

function PointDrawer({
  open,
  onClose,
  points,
  currentIndex,
  setCurrentIndex,
}) {
  const validatedCount =
    points.filter(isValidatedPoint).length;

  return (
    <>
      {open && (
        <div
          className="point-status-backdrop"
          onClick={onClose}
        />
      )}

      {open && (
        <aside
          className="point-status-panel"
          aria-label="Validation point status"
        >
          <div className="point-drawer-header">
            <div>
              <strong>
                VALIDATION STATUS
              </strong>

              <span>
                {validatedCount} /{" "}
                {points.length} checked
              </span>
            </div>

            <button
              type="button"
              className="drawer-close"
              onClick={onClose}
              aria-label="Close validation status"
            >
              ×
            </button>
          </div>

          <div className="drawer-progress">
            <div
              style={{
                width:
                  points.length > 0
                    ? `${
                        (validatedCount /
                          points.length) *
                        100
                      }%`
                    : "0%",
              }}
            />
          </div>

          <div className="drawer-summary">
            <span className="status-key">
              <i className="status-dot done" />
              Validated
            </span>

            <span className="status-key">
              <i className="status-dot undone" />
              Not validated
            </span>
          </div>

          <div className="drawer-list">
            {points.length === 0 ? (
              <div className="drawer-empty">
                No validation points loaded.
              </div>
            ) : (
              points.map(
                (point, index) => {
                  const validated =
                    isValidatedPoint(
                      point
                    );

                  const current =
                    index ===
                    currentIndex;

                  return (
                    <button
                      type="button"
                      key={
                        point.index ??
                        index
                      }
                      className={`drawer-point ${
                        current
                          ? "current"
                          : ""
                      } ${
                        validated
                          ? "done"
                          : "undone"
                      }`}
                      onClick={() => {
                        setCurrentIndex(
                          index
                        );

                        onClose();
                      }}
                    >
                      <span className="drawer-point-info">
                        <strong>
                          Point {index + 1}
                        </strong>
                      </span>

                      <span
                        className="drawer-point-status"
                        title={
                          validated
                            ? "Validated"
                            : "Not validated"
                        }
                      >
                        {validated
                          ? "✓"
                          : "×"}
                      </span>
                    </button>
                  );
                }
              )
            )}
          </div>
        </aside>
      )}
    </>
  );
}

/* =========================================================
VALIDATION PAGE
========================================================= */

function ValidationPage() {
  const [area, setArea] =
    useState("Agra");

  const [year, setYear] =
    useState("2018");

  const [lulcFile, setLulcFile] =
    useState(null);

  const [referenceFile, setReferenceFile] =
    useState(null);

  const [pointsFile, setPointsFile] =
    useState(null);

  const [points, setPoints] =
    useState([]);

  const [currentIndex, setCurrentIndex] =
    useState(0);

  const [lulcRaster, setLulcRaster] =
    useState(null);

  const [referenceRaster, setReferenceRaster] =
    useState(null);

  const [referenceClass, setReferenceClass] =
    useState(null);

  const [referenceSource, setReferenceSource] =
    useState("Sentinel-2");

  const [loading, setLoading] =
    useState(false);

  const [rasterLoading, setRasterLoading] =
    useState(false);

  const [message, setMessage] =
    useState("");

  const [pointDrawerOpen, setPointDrawerOpen] =
    useState(false);

  const currentPoint =
    points[currentIndex];

  /* =======================================================
  LOAD PROJECT
  ======================================================= */

  async function handleLoadProject() {
    if (
      !lulcFile ||
      !referenceFile ||
      !pointsFile
    ) {
      setMessage(
        "Please select the LULC TIFF, reference TIFF and validation CSV."
      );

      return;
    }

    try {
      setLoading(true);
      setMessage("");

      await loadProject({
        studyArea: area,
        year,
        lulcFile,
        referenceFile,
        pointsFile,
      });

      const loadedPoints =
        await getPoints();

      const safePoints =
        Array.isArray(loadedPoints)
          ? loadedPoints
          : [];

      setPoints(safePoints);

      const storageKey =
        `urbanflow_current_point_${area}_${year}`;

      const savedIndex = Number(
        localStorage.getItem(
          storageKey
        )
      );

      const restoredIndex =
        Number.isInteger(savedIndex)
          ? Math.max(
              0,
              Math.min(
                savedIndex,
                Math.max(
                  0,
                  safePoints.length - 1
                )
              )
            )
          : 0;

      setCurrentIndex(
        restoredIndex
      );

      setMessage(
        `Project loaded successfully. ${safePoints.length} validation points found.`
      );
    } catch (error) {
      console.error(
        "URBANFLOW project load error:",
        error
      );

      setMessage(
        error?.message ||
          "Failed to load project."
      );
    } finally {
      setLoading(false);
    }
  }

  /* =======================================================
  LOAD CURRENT POINT RASTER
  ======================================================= */

  async function loadCurrentPoint(
    point
  ) {
    if (!point) {
      setLulcRaster(null);
      setReferenceRaster(null);
      setReferenceClass(null);
      setReferenceSource(
        "Sentinel-2"
      );

      return;
    }

    try {
      setRasterLoading(true);
      setMessage("");

      const longitude =
        Number(point.longitude);

      const latitude =
        Number(point.latitude);

      if (
        !Number.isFinite(longitude) ||
        !Number.isFinite(latitude)
      ) {
        throw new Error(
          "Invalid validation point coordinates."
        );
      }

      const [
        lulc,
        reference,
      ] = await Promise.all([
        getRasterWindow(
          "lulc",
          longitude,
          latitude,
          100
        ),

        getRasterWindow(
          "reference",
          longitude,
          latitude,
          100
        ),
      ]);

      setLulcRaster(lulc);

      setReferenceRaster(
        reference
      );

      /* =================================================
         RESTORE VALIDATION
         ================================================= */

      const validated =
        isValidatedPoint(point);

      const dwClass =
        Number(point.dw_class);

      const savedReference =
        point.reference_class !==
          null &&
        point.reference_class !==
          undefined
          ? Number(
              point.reference_class
            )
          : null;

      setReferenceClass(
        validated &&
          Number.isFinite(
            savedReference
          )
          ? savedReference
          : Number.isFinite(
              dwClass
            )
          ? dwClass
          : null
      );

      setReferenceSource(
        validated &&
          point.reference_source
          ? point.reference_source
          : "Sentinel-2"
      );
    } catch (error) {
      console.error(
        "URBANFLOW raster error:",
        error
      );

      setMessage(
        error?.message ||
          "Failed to load raster window."
      );
    } finally {
      setRasterLoading(false);
    }
  }

  /* =======================================================
  POINT CHANGE + BROWSER PERSISTENCE
  ======================================================= */

  useEffect(() => {
    if (!points.length) return;

    const storageKey =
      `urbanflow_current_point_${area}_${year}`;

    localStorage.setItem(
      storageKey,
      String(currentIndex)
    );

    loadCurrentPoint(
      currentPoint
    );
  }, [
    currentIndex,
    points,
    area,
    year,
  ]);

  /* =======================================================
  RECOVER LOADED PROJECT / SESSION

   IMPORTANT:
   Do NOT use fetch("/api/project/info")
   here because production frontend and backend
   are hosted on different Render services.

   getProjectInfo() already uses VITE_API_BASE_URL
   and sends the JWT.
   ======================================================= */

  useEffect(() => {
    let cancelled = false;

    async function recoverProject() {
      try {
        const info =
          await getProjectInfo();

        if (
          cancelled ||
          !info?.points_loaded ||
          !info?.total_points
        ) {
          return;
        }

        const recoveredPoints =
          await getPoints();

        if (
          cancelled ||
          !Array.isArray(
            recoveredPoints
          ) ||
          !recoveredPoints.length
        ) {
          return;
        }

        const recoveredArea =
          info.study_area ||
          "Agra";

        const recoveredYear =
          String(
            info.year || "2018"
          );

        const storageKey =
          `urbanflow_current_point_${recoveredArea}_${recoveredYear}`;

        const savedIndex = Number(
          localStorage.getItem(
            storageKey
          )
        );

        const recoveredIndex =
          Number.isInteger(
            savedIndex
          )
            ? Math.max(
                0,
                Math.min(
                  savedIndex,
                  recoveredPoints.length -
                    1
                )
              )
            : 0;

        setArea(
          recoveredArea
        );

        setYear(
          recoveredYear
        );

        setPoints(
          recoveredPoints
        );

        setCurrentIndex(
          recoveredIndex
        );

        setMessage(
          `Recovered ${recoveredPoints.length} validation points. Previous review status restored.`
        );
      } catch (error) {
        console.debug(
          "URBANFLOW session recovery skipped:",
          error
        );
      }
    }

    recoverProject();

    return () => {
      cancelled = true;
    };
  }, []);

  /* =======================================================
  NAVIGATION
  ======================================================= */

  function previousPoint() {
    setCurrentIndex(
      (value) =>
        Math.max(
          0,
          value - 1
        )
    );
  }

  function nextPoint() {
    setCurrentIndex(
      (value) =>
        Math.min(
          Math.max(
            points.length - 1,
            0
          ),
          value + 1
        )
    );
  }

  /* =======================================================
  SAVE + VALIDATE

   IMPORTANT:
   Validation is now handled through api.js.
   No duplicate fetch() code belongs here.
   ======================================================= */

  async function savePoint(
    goNext = false
  ) {
    if (!currentPoint) return;

    if (
      referenceClass === null ||
      referenceClass === undefined
    ) {
      setMessage(
        "Please select a Reference Class before saving."
      );

      return;
    }

    if (!referenceSource) {
      setMessage(
        "Please select a Reference Source before saving."
      );

      return;
    }

    try {
      const result =
        await validatePoint(
          currentPoint.index,
          Number(
            referenceClass
          ),
          referenceSource
        );

      const updated =
        [...points];

      updated[currentIndex] = {
        ...updated[
          currentIndex
        ],

        reference_class:
          Number(
            referenceClass
          ),

        reference_source:
          referenceSource,

        validated: true,

        validation_status:
          "Validated",
      };

      setPoints(updated);

      setMessage(
        result?.message ||
          `Point ${
            currentIndex + 1
          } saved and validated.`
      );

      if (
        goNext &&
        currentIndex <
          points.length - 1
      ) {
        setCurrentIndex(
          (value) =>
            value + 1
        );
      }
    } catch (error) {
      console.error(
        "URBANFLOW save error:",
        error
      );

      setMessage(
        error?.message ||
          "Failed to save validation point."
      );
    }
  }

  /* =======================================================
  GOOGLE EARTH PRO
  ======================================================= */

  async function handleGoogleEarthPro() {
  if (!currentPoint) return;

  const pointId = Number(currentPoint.index);
  const latitude = Number(currentPoint.latitude);
  const longitude = Number(currentPoint.longitude);

  if (
    !Number.isFinite(pointId) ||
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude)
  ) {
    setMessage("Invalid validation point coordinates.");
    return;
  }

  const earthUrl =
    `urbanflow://open?lat=${encodeURIComponent(latitude)}` +
    `&lon=${encodeURIComponent(longitude)}` +
    `&point=${encodeURIComponent(pointId)}`;

  try {
    setMessage(
      `Opening Point ${pointId + 1} in Google Earth Pro...`
    );

    window.location.href = earthUrl;

  } catch (error) {
    console.error(
      "URBANFLOW Google Earth Pro error:",
      error
    );

    setMessage(
      "Could not open Google Earth Pro."
    );
  }
}

  /* =======================================================
  PROGRESS
  ======================================================= */

  const validatedCount =
    points.filter(
      isValidatedPoint
    ).length;

  const progress =
    points.length > 0
      ? (validatedCount /
          points.length) *
        100
      : 0;

  /* =======================================================
  UI
  ======================================================= */

  return (
    <div className="page">

      <PointDrawer
        open={pointDrawerOpen}
        onClose={() =>
          setPointDrawerOpen(
            (value) => !value
          )
        }
        points={points}
        currentIndex={
          currentIndex
        }
        setCurrentIndex={
          setCurrentIndex
        }
      />

      {/* =================================================
          SIDEBAR
         ================================================= */}

      <aside className="sidebar">

        <section className="sidebar-section compact-section">

          <h2>
            PROJECT CONFIGURATION
          </h2>

          <label>
            STUDY AREA
          </label>

          <select
            value={area}
            onChange={(event) =>
              setArea(
                event.target.value
              )
            }
          >
            <option value="Agra">
              Agra
            </option>

            <option value="Mathura">
              Mathura
            </option>

            <option value="Delhi">
              Delhi
            </option>
          </select>

          <label>
            YEAR
          </label>

          <select
            value={year}
            onChange={(event) =>
              setYear(
                event.target.value
              )
            }
          >
            {YEARS.map(
              (item) => (
                <option
                  key={item}
                  value={item}
                >
                  {item}
                </option>
              )
            )}
          </select>

        </section>

        {/* =================================================
            DATA
           ================================================= */}

        <section className="sidebar-section compact-section">

          <h2>
            DATA
          </h2>

          <FileSelector
            label="LULC GEOTIFF"
            file={lulcFile}
            setFile={setLulcFile}
            accept=".tif,.tiff"
          />

          <FileSelector
            label="REFERENCE GEOTIFF"
            file={referenceFile}
            setFile={
              setReferenceFile
            }
            accept=".tif,.tiff"
          />

          <FileSelector
            label="VALIDATION POINTS"
            file={pointsFile}
            
            /* FIXED:
               This must be the setter function,
               not the current file value.
            */
            setFile={setPointsFile}
            
            accept=".csv"
          />

          <button
            className="primary-button full-width"
            onClick={
              handleLoadProject
            }
            disabled={loading}
          >
            {loading
              ? "LOADING..."
              : "LOAD PROJECT"}
          </button>

        </section>

        {/* =================================================
            VALIDATION CONTROLS
           ================================================= */}

        <section className="sidebar-section compact-section validation-control-section">

          <h2>
            VALIDATION
          </h2>

          <div className="point-navigation">

            <button
              onClick={
                previousPoint
              }
              disabled={
                currentIndex ===
                  0 ||
                !points.length
              }
            >
              Previous
            </button>

            <div className="point-count">
              Point{" "}
              {points.length
                ? currentIndex +
                  1
                : 0}
              {" / "}
              {points.length}
            </div>

            <button
              onClick={
                nextPoint
              }
              disabled={
                !points.length ||
                currentIndex >=
                  points.length -
                    1
              }
            >
              Next
            </button>

          </div>

          <div className="progress-label">

            <span>
              Validation Progress
            </span>

            <span>
              {Math.round(
                progress
              )}
              %
            </span>

          </div>

          <div className="progress">

            <div
              style={{
                width: `${progress}%`,
              }}
            />

          </div>

          <button
            type="button"
            className="open-points-button"
            onClick={() =>
              setPointDrawerOpen(
                true
              )
            }
          >
            <span>
              VIEW VALIDATION STATUS
            </span>

            <strong>
              {validatedCount}/
              {points.length}
            </strong>
          </button>

        </section>

        {/* =================================================
            CURRENT POINT
           ================================================= */}

        {currentPoint && (
          <>

            <section className="sidebar-section compact-section">

              <h2>
                CURRENT POINT
              </h2>

              <div className="point-card">

                <div className="point-row">

                  <span>
                    LAT
                  </span>

                  <strong>
                    {safeNumber(
                      currentPoint.latitude
                    ).toFixed(6)}
                  </strong>

                </div>

                <div className="point-row">

                  <span>
                    LON
                  </span>

                  <strong>
                    {safeNumber(
                      currentPoint.longitude
                    ).toFixed(6)}
                  </strong>

                </div>

                <div className="point-row">

                  <span>
                    DYNAMIC WORLD
                  </span>

                  <strong>
                    {
                      currentPoint.dw_class
                    }{" "}
                    —{" "}
                    {className(
                      currentPoint.dw_class
                    )}
                  </strong>

                </div>

                <div className="point-row">

                  <span>
                    STATUS
                  </span>

                  <strong
                    className={
                      isValidatedPoint(
                        currentPoint
                      )
                        ? "status-good"
                        : "status-bad"
                    }
                  >
                    {isValidatedPoint(
                      currentPoint
                    )
                      ? "Validated"
                      : "Not validated"}
                  </strong>

                </div>

              </div>

              <button
                type="button"
                className="earth-button"
                onClick={
                  handleGoogleEarthPro
                }
              >
                OPEN CURRENT POINT IN GOOGLE EARTH PRO
              </button>

            </section>

            {/* =================================================
                REFERENCE CLASS
               ================================================= */}

            <section className="sidebar-section compact-section">

              <div className="section-title-row">

                <h2>
                  REFERENCE CLASS
                </h2>

                <span className="auto-reference-badge">
                  {currentPoint.dw_class !==
                  undefined
                    ? `DEFAULT: ${currentPoint.dw_class}`
                    : "DEFAULT"}
                </span>

              </div>

              <div className="class-list compact-class-list">

                {CLASSES.map(
                  (item) => (
                    <label
                      key={
                        item.id
                      }
                      className={
                        referenceClass ===
                        item.id
                          ? "class-selected"
                          : ""
                      }
                    >

                      <input
                        type="radio"
                        name="reference-class"
                        checked={
                          referenceClass ===
                          item.id
                        }
                        onChange={() =>
                          setReferenceClass(
                            item.id
                          )
                        }
                      />

                      <span>
                        {item.id} —{" "}
                        {item.name}
                      </span>

                    </label>
                  )
                )}

              </div>

            </section>

            {/* =================================================
                REFERENCE SOURCE
               ================================================= */}

            <section className="sidebar-section compact-section">

              <h2>
                REFERENCE SOURCE
              </h2>

              <select
                value={
                  referenceSource
                }
                onChange={(event) =>
                  setReferenceSource(
                    event.target.value
                  )
                }
              >

                <option value="Sentinel-2">
                  Sentinel-2
                </option>

                <option value="Google Earth Pro">
                  Google Earth Pro
                </option>

                <option value="Other">
                  Other
                </option>

              </select>

              <button
                className="primary-button full-width save-next-button"
                onClick={() =>
                  savePoint(true)
                }
              >
                SAVE &amp; NEXT
              </button>

              <button
                className="secondary-button full-width"
                onClick={() =>
                  savePoint(false)
                }
              >
                SAVE ONLY
              </button>

            </section>

          </>
        )}

        {message && (
          <div className="status-message">
            {message}
          </div>
        )}

      </aside>

      {/* =================================================
          MAIN MAP AREA
         ================================================= */}

      <main className="validation-main">

        <div className="validation-title">

          <div>

            <h1>
              {area} / {year} —
              LULC Validation
            </h1>

            {currentPoint && (
              <p>
                Point{" "}
                {currentIndex + 1} —{" "}
                {safeNumber(
                  currentPoint.latitude
                ).toFixed(6)}
                ,{" "}
                {safeNumber(
                  currentPoint.longitude
                ).toFixed(6)}
              </p>
            )}

          </div>

          {rasterLoading && (
            <span className="loading-text">
              Loading raster window...
            </span>
          )}

        </div>

        <div className="dual-view">

          {/* =================================================
              LULC
             ================================================= */}

          <section className="map-panel">

            <div className="map-header">

              <div>
                ORIGINAL LULC GEOTIFF
              </div>

              <span>
                Dynamic World
              </span>

            </div>

            <div className="map-container">

              <RasterCanvas
                raster={
                  lulcRaster
                }
                type="lulc"
                pointNumber={
                  currentIndex + 1
                }
              />

            </div>

            <div className="map-footer">

              <span>
                Dynamic World LULC classes
              </span>

              {currentPoint && (
                <span>
                  Point centered
                </span>
              )}

            </div>

          </section>

          {/* =================================================
              REFERENCE
             ================================================= */}

          <section className="map-panel">

            <div className="map-header">

              <div>
                REFERENCE — B4 / B3 / B2
              </div>

              <span>
                Sentinel-2
              </span>

            </div>

            <div className="map-container">

              <RasterCanvas
                raster={
                  referenceRaster
                }
                type="reference"
                pointNumber={
                  currentIndex + 1
                }
              />

            </div>

            <div className="map-footer">

              <span>
                Sentinel-2 reference imagery
              </span>

              {currentPoint && (
                <span>
                  Same coordinates
                </span>
              )}

            </div>

          </section>

        </div>

      </main>

    </div>
  );
}

/* =========================================================
RESULTS PAGE
========================================================= */

function ResultsPage({
  setPage,
  active,
}) {
  const [results, setResults] =
    useState(null);

  const [message, setMessage] =
    useState("");

  async function loadResults() {
    try {
      const data =
        await getValidationResults();

      setResults(data);
    } catch (error) {
      console.error(
        "URBANFLOW results error:",
        error
      );

      setMessage(
        error?.message ||
          "Could not load validation results."
      );
    }
  }

  useEffect(() => {
    if (active) {
      loadResults();
    }
  }, [active]);

  async function handleExport() {
    try {
      const result =
        await exportValidation();

      setMessage(
        result?.message ||
          "Validation exported successfully."
      );
    } catch (error) {
      setMessage(
        error?.message ||
          "Export failed."
      );
    }
  }

  if (!results) {
    return (
      <main className="results-page">

        <h1>
          Validation Results
        </h1>

        <p>
          {message ||
            "No validation results available yet."}
        </p>

        <button
          className="secondary-button"
          onClick={() =>
            setPage("validation")
          }
        >
          Back to Validation
        </button>

      </main>
    );
  }

  return (
    <main className="results-page">

      <div className="results-heading">

        <div>

          <h1>
            Validation Results
          </h1>

          <p>
            {results.total_samples}{" "}
            validated samples
          </p>

        </div>

        <div className="results-actions">

          <button
            className="secondary-button"
            onClick={() =>
              setPage("validation")
            }
          >
            Back to Validation
          </button>

          <button
            className="primary-button"
            onClick={
              handleExport
            }
          >
            EXPORT CSV
          </button>

        </div>

      </div>

      {message && (
        <div className="status-message">
          {message}
        </div>
      )}

      {/* =================================================
          METRICS
         ================================================= */}

      <div className="metric-grid">

        <div className="metric-card overall-accuracy-card">

          <span>
            Overall Accuracy
          </span>

          <strong>
            {(
              safeNumber(
                results.overall_accuracy
              ) * 100
            ).toFixed(2)}
            %
          </strong>

        </div>

        <div className="metric-card">

          <span>
            Kappa
          </span>

          <strong>
            {safeNumber(
              results.kappa
            ).toFixed(4)}
          </strong>

        </div>

        <div className="metric-card">

          <span>
            Validated Points
          </span>

          <strong>
            {results.total_samples}
          </strong>

        </div>

        <div className="metric-card">

          <span>
            Correct Samples
          </span>

          <strong>
            {results.correct_samples}
          </strong>

        </div>

      </div>

      {/* =================================================
          CONFUSION MATRIX
         ================================================= */}

      <section className="result-card">

        <h2>
          CONFUSION MATRIX
        </h2>

        <div className="matrix-wrapper">

          <table className="matrix">

            <thead>

              <tr>

                <th>
                  Reference ↓ / DW →
                </th>

                {CLASSES.map(
                  (item) => (
                    <th
                      key={
                        item.id
                      }
                    >
                      {item.id}
                    </th>
                  )
                )}

              </tr>

            </thead>

            <tbody>

              {(
                results.confusion_matrix ||
                []
              ).map(
                (row, rowIndex) => (
                  <tr
                    key={
                      rowIndex
                    }
                  >

                    <th>
                      {rowIndex}
                    </th>

                    {row.map(
                      (
                        value,
                        columnIndex
                      ) => (
                        <td
                          key={
                            columnIndex
                          }
                          className={
                            rowIndex ===
                            columnIndex
                              ? "diagonal"
                              : ""
                          }
                        >
                          {value}
                        </td>
                      )
                    )}

                  </tr>
                )
              )}

            </tbody>

          </table>

        </div>

      </section>

      {/* =================================================
          CLASS ACCURACY
         ================================================= */}

      <section className="result-card">

        <h2>
          CLASS-WISE ACCURACY
        </h2>

        <table className="accuracy-table">

          <thead>

            <tr>

              <th>
                Class
              </th>

              <th>
                Reference Total
              </th>

              <th>
                DW Total
              </th>

              <th>
                Correct
              </th>

              <th>
                Producer Accuracy
              </th>

              <th>
                User Accuracy
              </th>

            </tr>

          </thead>

          <tbody>

            {(
              results.class_metrics ||
              []
            ).map(
              (item) => (
                <tr
                  key={
                    item.class_id
                  }
                >

                  <td>
                    {item.class_id} —{" "}
                    {item.class_name}
                  </td>

                  <td>
                    {
                      item.reference_total
                    }
                  </td>

                  <td>
                    {
                      item.dw_total
                    }
                  </td>

                  <td>
                    {
                      item.correct
                    }
                  </td>

                  <td>
                    {(
                      safeNumber(
                        item.producer_accuracy
                      ) * 100
                    ).toFixed(2)}
                    %
                  </td>

                  <td>
                    {(
                      safeNumber(
                        item.user_accuracy
                      ) * 100
                    ).toFixed(2)}
                    %
                  </td>

                </tr>
              )
            )}

          </tbody>

        </table>

      </section>

    </main>
  );
}

/* =========================================================
HISTORY PAGE
========================================================= */

function HistoryPage({
  active,
}) {
  const [history, setHistory] =
    useState([]);

  const [message, setMessage] =
    useState("");

  useEffect(() => {
    async function load() {
      try {
        const data =
          await getHistory();

        setHistory(
          Array.isArray(data)
            ? data
            : []
        );
      } catch (error) {
        console.error(
          "URBANFLOW history error:",
          error
        );

        setMessage(
          error?.message ||
            "Could not load history."
        );
      }
    }

    if (active) {
      load();
    }
  }, [active]);

  return (
    <main className="history-page">

      <div className="results-heading">

        <div>

          <h1>
            Validation History
          </h1>

          <p>
            Previously completed URBANFLOW validation sessions
          </p>

        </div>

      </div>

      {message && (
        <div className="status-message">
          {message}
        </div>
      )}

      <section className="result-card">

        {history.length === 0 ? (

          <div className="empty-history">
            No validation sessions have
            been exported yet.
          </div>

        ) : (

          <div className="history-table-wrapper">

            <table className="accuracy-table">

              <thead>

                <tr>

                  <th>
                    Area
                  </th>

                  <th>
                    Year
                  </th>

                  <th>
                    Total Points
                  </th>

                  <th>
                    Validated
                  </th>

                  <th>
                    Accuracy
                  </th>

                  <th>
                    Kappa
                  </th>

                  <th>
                    Date
                  </th>

                </tr>

              </thead>

              <tbody>

                {history.map(
                  (
                    item,
                    index
                  ) => (

                    <tr
                      key={
                        index
                      }
                    >

                      <td>
                        {item.area}
                      </td>

                      <td>
                        {item.year}
                      </td>

                      <td>
                        {
                          item.total_points
                        }
                      </td>

                      <td>
                        {
                          item.validated_points
                        }
                      </td>

                      <td>
                        {(
                          safeNumber(
                            item.overall_accuracy
                          ) * 100
                        ).toFixed(2)}
                        %
                      </td>

                      <td>
                        {safeNumber(
                          item.kappa
                        ).toFixed(4)}
                      </td>

                      <td>
                        {item.timestamp}
                      </td>

                    </tr>

                  )
                )}

              </tbody>

            </table>

          </div>

        )}

      </section>

    </main>
  );
}

/* =========================================================
MAIN APP
========================================================= */

export default function App() {
  const [page, setPage] =
    useState("validation");

  const [user, setUser] =
    useState(() => {
      try {
        const savedUser =
          localStorage.getItem(
            "urbanflow_user"
          );

        return savedUser
          ? JSON.parse(
              savedUser
            )
          : null;
      } catch {
        return null;
      }
    });

  function handleLogin(
    loggedInUser
  ) {
    setUser(
      loggedInUser
    );
  }

  function handleLogout() {
    localStorage.removeItem(
      "urbanflow_access_token"
    );

    localStorage.removeItem(
      "urbanflow_user"
    );

    setUser(null);
  }

  if (!user) {
    return (
      <Login
        onLogin={
          handleLogin
        }
      />
    );
  }

  return (
    <div className="app">

      <Header
        page={page}
        setPage={setPage}
      />

      <div
        style={{
          display:
            page ===
            "validation"
              ? "block"
              : "none",
        }}
      >
        <ValidationPage />
      </div>

      <div
        style={{
          display:
            page === "results"
              ? "block"
              : "none",
        }}
      >
        <ResultsPage
          setPage={
            setPage
          }
          active={
            page === "results"
          }
        />
      </div>

      <div
        style={{
          display:
            page === "history"
              ? "block"
              : "none",
        }}
      >
        <HistoryPage
          active={
            page === "history"
          }
        />
      </div>

    </div>
  );
}