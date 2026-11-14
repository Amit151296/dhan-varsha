import apiClient from "./client";

export async function getPortfolio() {
  const { data } = await apiClient.get("/api/portfolio");
  return data;
}

export async function uploadPortfolioScreenshot(file, { broker } = {}) {
  const formData = new FormData();
  formData.append("file", file);
  if (broker) formData.append("broker", broker);
  const { data } = await apiClient.post("/api/portfolio/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getPortfolioAnalysis({ broker } = {}) {
  const { data } = await apiClient.get("/api/portfolio/analysis", {
    params: broker ? { broker } : {},
  });
  return data;
}

export async function fetchPortfolioMetrics({ forceRefresh = false, broker } = {}) {
  const { data } = await apiClient.post("/api/portfolio/metrics", null, {
    params: { force_refresh: forceRefresh, ...(broker ? { broker } : {}) },
  });
  return data;
}

export async function syncPortfolioPrices() {
  const { data } = await apiClient.post("/api/portfolio/sync");
  return data;
}

export async function addHolding(holding) {
  const { data } = await apiClient.post("/api/portfolio/holdings", holding);
  return data;
}

export async function updateHolding(holdingId, patch) {
  const { data } = await apiClient.patch(`/api/portfolio/holdings/${holdingId}`, patch);
  return data;
}

export async function deleteHolding(holdingId) {
  await apiClient.delete(`/api/portfolio/holdings/${holdingId}`);
}

export async function listPortfolioUploads() {
  const { data } = await apiClient.get("/api/portfolio/uploads");
  return data;
}

export async function downloadPortfolioReport({ broker, format = "html" } = {}) {
  const response = await apiClient.get("/api/portfolio/report", {
    params: { format, ...(broker ? { broker } : {}) },
    responseType: "blob",
  });
  const disposition = response.headers["content-disposition"] || "";
  const filename = /filename="?([^";]+)"?/.exec(disposition)?.[1] || `portfolio_report.${format}`;
  const url = window.URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

export async function fetchPortfolioInsights(jobId, { refresh = false } = {}) {
  const { data } = await apiClient.post(`/api/portfolio/metrics/${jobId}/insights`, null, {
    params: { refresh },
  });
  return data;
}
