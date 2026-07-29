// In production, set VITE_API_URL to the deployed backend origin
// (e.g. https://your-backend.onrender.com). Locally it's empty, so calls
// go to /api and the vite dev proxy forwards them to localhost:8000.
const API_BASE = import.meta.env.VITE_API_URL || "";

export function apiUrl(path) {
  return `${API_BASE}${path}`;
}
