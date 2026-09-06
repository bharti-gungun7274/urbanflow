# URBANFLOW — Full Stack LULC Validation

## What changed

- React + Leaflet replaces CSS-positioned raster maps.
- The original LULC raster and categorical colour rendering use the same GeoTIFF bounds.
- The validation marker is a geographic latitude/longitude marker, so it stays on the correct location while zooming and panning.
- Left and right maps are synchronized.
- The backend searches the entire `data/` directory recursively and tolerates case, spaces and common filename variations. This fixes common Delhi filename/path problems.
- NoData value 255 is transparent in the colour-coded raster.
- Validation saving and OA/Kappa/confusion-matrix calculations are retained.
- The frontend keeps the existing URBANFLOW black/white interface.

## Data

Put your files in:

```text
data/
  Delhi_LULC_2018.tif
  Delhi_Validation_Points_2018.csv
  Mathura_LULC_2018.tif
  Mathura_Validation_Points_2018.csv
  Agra_LULC_2018.tif
  Agra_Validation_Points_2018.csv
```

Nested folders are also supported.

## Backend

From the project root:

```powershell
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

If you see `'vite' is not recognized`, run `npm install` inside `frontend` first.

## Important

Run the backend command from the `urbanflow_final` project root, not from inside `backend`.
