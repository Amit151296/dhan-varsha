import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <h1>Dhan Varsha</h1>
        <button onClick={handleLogout}>Log Out</button>
      </header>
      <main>
        <h2>Welcome, {user?.full_name}</h2>
        <p>Your stock investment guide dashboard will appear here.</p>
      </main>
    </div>
  );
}
