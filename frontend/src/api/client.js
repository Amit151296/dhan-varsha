import axios from "axios";

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000",
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("dhanvarsha_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A 401 on any non-auth call means the login token has expired (they last an hour).
// Without this the stale user in localStorage keeps the app looking logged in while
// every request fails, so drop the session and send the user to log in again.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error.config?.url || "";
    if (error.response?.status === 401 && !url.startsWith("/api/auth/")) {
      localStorage.removeItem("dhanvarsha_token");
      localStorage.removeItem("dhanvarsha_user");
      try {
        sessionStorage.setItem("dhanvarsha_session_expired", "1");
      } catch {
        // sessionStorage can be blocked; the redirect still happens.
      }
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

export default apiClient;
