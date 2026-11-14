import apiClient from "./client";

export async function getIndexPerformance() {
  const { data } = await apiClient.get("/api/market/indices");
  return data;
}

export async function getIndexCompanies(slug) {
  const { data } = await apiClient.get(`/api/market/indices/${encodeURIComponent(slug)}/companies`);
  return data;
}

export async function downloadIndexPerformance() {
  const response = await apiClient.get("/api/market/indices/export", { responseType: "blob" });
  const disposition = response.headers["content-disposition"] || "";
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] || "NSE_index_performance.xlsx";
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
