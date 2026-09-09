const API_BASE =
  import.meta.env.VITE_API_BASE_URL ||
  "http://127.0.0.1:8000/api";

/* ============================================================
   GENERIC API REQUEST
   ============================================================ */

async function request(url, options = {}) {
  const token = localStorage.getItem(
    "urbanflow_access_token"
  );

  const headers = {
    ...(options.headers || {}),
  };

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
        `Request failed with status ${response.status}`
    );
  }

  return data;
}

/* ============================================================
   FILE DOWNLOAD
   ============================================================ */

async function downloadRequest(url) {
  const token = localStorage.getItem(
    "urbanflow_access_token"
  );

  const headers = {};

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(
    `${API_BASE}${url}`,
    {
      method: "GET",
      headers,
    }
  );

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
    let detail = null;

    try {
      const data = await response.json();
      detail = data?.detail;
    } catch {
      detail = null;
    }

    throw new Error(
      detail ||
        `Download failed with status ${response.status}`
    );
  }

  const blob = await response.blob();

  const disposition =
    response.headers.get(
      "Content-Disposition"
    ) || "";

  const match =
    disposition.match(
      /filename="?([^"]+)"?/i
    );

  const filename =
    match?.[1] ||
    "urbanflow_validation_export";

  const objectUrl =
    window.URL.createObjectURL(blob);

  const link =
    document.createElement("a");

  link.href = objectUrl;
  link.download = filename;

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(
    objectUrl
  );

  return {
    status: "success",
    filename,
  };
}

/* ============================================================
   PROJECT
   ============================================================ */

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

/* ============================================================
   VALIDATION POINTS
   ============================================================ */

export async function getPoints() {
  return request(
    "/points"
  );
}

export async function getPoint(index) {
  return request(
    `/points/${index}`
  );
}

/* ============================================================
   REFERENCE CLASS
   ============================================================ */

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
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        reference_class:
          Number(referenceClass),

        reference_source:
          referenceSource,
      }),
    }
  );
}

/* ============================================================
   VALIDATE POINT
   ============================================================ */

export async function validatePoint(
  index,
  referenceClass,
  referenceSource
) {
  return request(
    `/points/${index}/validate`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        reference_class:
          Number(referenceClass),

        reference_source:
          referenceSource,
      }),
    }
  );
}

/* ============================================================
   RASTER
   ============================================================ */

export async function getRasterWindow(
  kind,
  longitude,
  latitude,
  radiusPixels = 80
) {
  const params = new URLSearchParams({
    kind,
    longitude,
    latitude,
    radius_pixels: radiusPixels,
  });

  return request(
    `/raster/window?${params.toString()}`
  );
}

export async function getRasterInfo(kind) {
  return request(
    `/raster/info?kind=${kind}`
  );
}

/* ============================================================
   GOOGLE EARTH
   ============================================================ */

export async function openGoogleEarth(index) {
  return request(
    `/points/${index}/google-earth`,
    {
      method: "POST",
    }
  );
}

/* ============================================================
   VALIDATION RESULTS
   ============================================================ */

export async function getValidationResults(
  area,
  year
) {
  const params = new URLSearchParams({
    area: String(area),
    year: String(year),
  });

  return request(
    `/validation/results?${params.toString()}`
  );
}

/* ============================================================
   VALIDATION EXPORTS
   ============================================================ */

export async function downloadValidatedPoints(
  area,
  year
) {
  const params = new URLSearchParams({
    area: String(area),
    year: String(year),
  });

  return downloadRequest(
    `/validation/export/validated-points?${params.toString()}`
  );
}

export async function downloadConfusionMatrix(
  area,
  year
) {
  const params = new URLSearchParams({
    area: String(area),
    year: String(year),
  });

  return downloadRequest(
    `/validation/export/confusion-matrix?${params.toString()}`
  );
}

export async function downloadClassAccuracy(
  area,
  year
) {
  const params = new URLSearchParams({
    area: String(area),
    year: String(year),
  });

  return downloadRequest(
    `/validation/export/class-accuracy?${params.toString()}`
  );
}

export async function downloadValidationSummary(
  area,
  year
) {
  const params = new URLSearchParams({
    area: String(area),
    year: String(year),
  });

  return downloadRequest(
    `/validation/export/summary?${params.toString()}`
  );
}

export async function downloadCompleteValidationPackage(
  area,
  year
) {
  const params = new URLSearchParams({
    area: String(area),
    year: String(year),
  });

  return downloadRequest(
    `/validation/export/complete?${params.toString()}`
  );
}

/* ============================================================
   LEGACY SERVER EXPORT
   ============================================================ */

export async function exportValidation(
  area,
  year
) {
  const params = new URLSearchParams({
    area: String(area),
    year: String(year),
  });

  return request(
    `/validation/export?${params.toString()}`,
    {
      method: "POST",
    }
  );
}

/* ============================================================
   HISTORY
   ============================================================ */

export async function getHistory() {
  return request(
    "/history"
  );
}

/* ============================================================
   ACTIVE USERS
   ============================================================ */

/*
   Sends a heartbeat for the currently logged-in user.

   The backend uses this to determine that the user
   is currently active/working.
*/

export async function heartbeatActiveUser() {
  return request(
    "/active-users/heartbeat",
    {
      method: "POST",
    }
  );
}

/*
   Gets only active working-session information.

   Example response:

   [
     {
       username: "bhagun74",
       area: "Agra",
       year: 2018,
       status: "Active"
     }
   ]

   No validation records are returned.
*/

export async function getActiveUsers() {
  return request(
    "/active-users"
  );
}

/* ============================================================
   HEALTH
   ============================================================ */

export async function healthCheck() {
  return request(
    "/health"
  );
}