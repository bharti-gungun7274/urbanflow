import React, { useState } from "react";
import "./Login.css";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "http://127.0.0.1:8000";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(event) {
    event.preventDefault();

    if (!username.trim() || !password) {
      setMessage("Please enter username and password.");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      const response = await fetch(
        `${API_BASE_URL}/auth/login`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            username: username.trim(),
            password,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail || "Invalid username or password."
        );
      }

      localStorage.setItem(
        "urbanflow_access_token",
        data.access_token
      );

      localStorage.setItem(
        "urbanflow_user",
        JSON.stringify(data.user)
      );

      onLogin(data.user);
    } catch (error) {
      setMessage(
        error?.message ||
          "Login failed. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">

        <div className="login-brand-mark">
          UF
        </div>

        <h1>URBANFLOW</h1>

        <p className="login-subtitle">
          YAMUNA URBANIZATION &amp; WATER QUALITY RESEARCH
        </p>

        <div className="login-divider" />

        <h2>RESEARCH VALIDATION SYSTEM</h2>

        <form onSubmit={handleLogin}>

          <label>USERNAME</label>

          <input
            type="text"
            value={username}
            onChange={(event) =>
              setUsername(event.target.value)
            }
            autoComplete="username"
            placeholder="Enter username"
          />

          <label>PASSWORD</label>

          <input
            type="password"
            value={password}
            onChange={(event) =>
              setPassword(event.target.value)
            }
            autoComplete="current-password"
            placeholder="Enter password"
          />

          {message && (
            <div className="login-message">
              {message}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
          >
            {loading ? "SIGNING IN..." : "SIGN IN"}
          </button>

        </form>

        <div className="login-footer">
          Authorized URBANFLOW research users only
        </div>

      </div>
    </div>
  );
}