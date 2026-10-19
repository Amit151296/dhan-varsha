import apiClient from "./client";

export async function fetchSectors() {
  const { data } = await apiClient.get("/api/screener/sectors");
  return data;
}

export async function runFetch(sectorKey, { forceRefresh = false } = {}) {
  const { data } = await apiClient.post("/api/screener/fetch", {
    sector_key: sectorKey,
    force_refresh: forceRefresh,
  });
  return data;
}

export async function listJobs(limit = 20) {
  const { data } = await apiClient.get("/api/screener/jobs", { params: { limit } });
  return data;
}

export async function getJob(jobId) {
  const { data } = await apiClient.get(`/api/screener/jobs/${jobId}`);
  return data;
}

export async function downloadExport(jobId, filename) {
  const response = await apiClient.get(`/api/screener/jobs/${jobId}/export`, {
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
