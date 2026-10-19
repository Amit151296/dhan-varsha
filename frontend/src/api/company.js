import apiClient from "./client";

export async function searchCompanies(query) {
  const { data } = await apiClient.get("/api/company/search", { params: { q: query } });
  return data;
}

export async function resolveCompanyByName(name) {
  const { data } = await apiClient.post("/api/company/resolve", { name });
  return data;
}

export async function analyseCompany(url, { companyName, forceRefresh = false } = {}) {
  const { data } = await apiClient.post("/api/company/analyse", {
    url,
    company_name: companyName,
    force_refresh: forceRefresh,
  });
  return data;
}
