const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "http://127.0.0.1:8000/api";


async function request(url, options = {}) {

  const token = localStorage.getItem(
    "urbanflow_access_token"
  );


  const headers = {
    ...(options.headers || {}),
  };


  // ----------------------------------------------------------
  // Add JWT authentication to every protected API request
  // ----------------------------------------------------------

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }


  const response = await fetch(
    `${API_BASE}${url}`,
    {
      ...options,
      headers,
    }
  );


  // ----------------------------------------------------------
  // Read response safely
  // ----------------------------------------------------------

  let data = null;

  try {
    data = await response.json();
  } catch {
    data = null;
  }


  // ----------------------------------------------------------
  // Authentication failure
  // ----------------------------------------------------------

  if (response.status === 401) {

    localStorage.removeItem(
      "urbanflow_access_token"
    );

    localStorage.removeItem(
      "urbanflow_user"
    );

    throw new Error(
      "Your login session has expired. Please sign in again."
    );
  }


  // ----------------------------------------------------------
  // Other API errors
  // ----------------------------------------------------------

  if (!response.ok) {

    throw new Error(
      data?.detail ||
      `Request failed with status ${response.status}`
    );
  }


  return data;
}


// ============================================================
// PROJECT
// ============================================================

export async function loadProject({
  studyArea,
  year,
  lulcFile,
  pointsFile,
  referenceFile,
}) {

  const formData = new FormData();


  formData.append(
    "study_area",
    studyArea
  );


  formData.append(
    "year",
    year
  );


  formData.append(
    "lulc_file",
    lulcFile
  );


  formData.append(
    "points_file",
    pointsFile
  );


  formData.append(
    "reference_file",
    referenceFile
  );


  return request(
    "/project/load",
    {
      method: "POST",
      body: formData,
    }
  );
}


export async function getProjectInfo() {

  return request(
    "/project/info"
  );
}


// ============================================================
// VALIDATION POINTS
// ============================================================

export async function getPoints() {

  return request(
    "/points"
  );
}


export async function getPoint(
  index
) {

  return request(
    `/points/${index}`
  );
}


// ============================================================
// REFERENCE CLASS
// ============================================================

export async function updateReferenceClass(
  index,
  referenceClass,
  referenceSource
) {

  return request(
    `/points/${index}/reference`,
    {
      method: "PUT",

      headers: {
        "Content-Type":
          "application/json",
      },

      body: JSON.stringify({

        reference_class:
          referenceClass,

        reference_source:
          referenceSource,
      }),
    }
  );
}


// ============================================================
// RASTER
// ============================================================

export async function getRasterWindow(
  kind,
  longitude,
  latitude,
  radiusPixels = 80
) {

  const params =
    new URLSearchParams({

      kind,

      longitude,

      latitude,

      radius_pixels:
        radiusPixels,
    });


  return request(
    `/raster/window?${params.toString()}`
  );
}


export async function getRasterInfo(
  kind
) {

  return request(
    `/raster/info?kind=${kind}`
  );
}


// ============================================================
// GOOGLE EARTH
// ============================================================

export async function openGoogleEarth(
  index
) {

  return request(
    `/points/${index}/google-earth`,
    {
      method: "POST",
    }
  );
}


// ============================================================
// VALIDATION RESULTS
// ============================================================

export async function getValidationResults() {

  return request(
    "/validation/results"
  );
}


export async function exportValidation() {
  const token = localStorage.getItem(
    "urbanflow_access_token"
  );

  const response = await fetch(
    `${API_BASE}/validation/export`,
    {
      method: "POST",
      headers: {
        ...(token
          ? {
              Authorization: `Bearer ${token}`,
            }
          : {}),
      },
    }
  );

  let data = null;

  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (response.status === 401) {
    localStorage.removeItem(
      "urbanflow_access_token"
    );

    localStorage.removeItem(
      "urbanflow_user"
    );

    throw new Error(
      "Your login session has expired. Please sign in again."
    );
  }

  if (!response.ok) {
    throw new Error(
      data?.detail ||
        `Export failed with status ${response.status}`
    );
  }

  return data;
}


// ============================================================
// HISTORY
// ============================================================

export async function getHistory() {

  return request(
    "/history"
  );
}


// ============================================================
// HEALTH
// ============================================================

export async function healthCheck() {

  return request(
    "/health"
  );
}