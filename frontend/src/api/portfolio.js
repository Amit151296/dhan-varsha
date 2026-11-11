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

export async function getPortfolioAnalysis() {
  const { data } = await apiClient.get("/api/portfolio/analysis");
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
