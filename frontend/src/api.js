// FIX: VITE_API_URL must be set in Vercel Environment Variables as:
//   VITE_API_URL = https://ora-oovf.onrender.com
// Vite bakes env vars at build time — the fallback only applies locally.
const API = import.meta.env.VITE_API_URL || "http://localhost:8000"

export default API