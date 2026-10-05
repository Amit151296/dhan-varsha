import { createContext, useContext, useEffect, useState } from "react";
import apiClient from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const storedUser = localStorage.getItem("dhanvarsha_user");
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    setLoading(false);
  }, []);

  function persistSession(data) {
    localStorage.setItem("dhanvarsha_token", data.access_token);
    localStorage.setItem("dhanvarsha_user", JSON.stringify(data.user));
    setUser(data.user);
  }

  async function login(email, password) {
    const { data } = await apiClient.post("/api/auth/login", { email, password });
    persistSession(data);
  }

  async function register(fullName, email, password) {
    const { data } = await apiClient.post("/api/auth/register", {
      full_name: fullName,
      email,
      password,
    });
    persistSession(data);
  }

  function logout() {
    localStorage.removeItem("dhanvarsha_token");
    localStorage.removeItem("dhanvarsha_user");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
