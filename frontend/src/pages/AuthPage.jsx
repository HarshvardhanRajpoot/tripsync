import { useState } from "react";
import { useAuth } from "../context/AuthContext";

export default function AuthPage() {
  const { signup, login } = useAuth();
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function update(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      if (mode === "signup") {
        await signup(form);
      } else {
        await login({ email: form.email, password: form.password });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={styles.page}>
      <div style={styles.stub}>
        <p style={styles.eyebrow}>TripSync · Group Travel Planner</p>
        <h1 style={styles.wordmark}>TripSync</h1>
        <p style={styles.tagline}>
          Plan the trip together — one shared budget, one plan everyone agrees on.
        </p>
      </div>

      <hr className="perforation" style={{ margin: "0 40px" }} />

      <div style={styles.formWrap}>
        <div style={styles.tabs}>
          <button
            type="button"
            onClick={() => setMode("login")}
            style={{ ...styles.tab, ...(mode === "login" ? styles.tabActive : {}) }}
          >
            Log in
          </button>
          <button
            type="button"
            onClick={() => setMode("signup")}
            style={{ ...styles.tab, ...(mode === "signup" ? styles.tabActive : {}) }}
          >
            Sign up
          </button>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          {mode === "signup" && (
            <div className="field">
              <label htmlFor="name">Name</label>
              <input
                id="name"
                type="text"
                required
                value={form.name}
                onChange={update("name")}
                placeholder="Your name"
              />
            </div>
          )}

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              required
              value={form.email}
              onChange={update("email")}
              placeholder="you@example.com"
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              required
              minLength={6}
              value={form.password}
              onChange={update("password")}
              placeholder="At least 6 characters"
            />
          </div>

          <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={submitting}>
            {submitting ? "Please wait…" : mode === "signup" ? "Create account" : "Log in"}
          </button>
        </form>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "24px",
  },
  stub: {
    maxWidth: 420,
    width: "100%",
    background: "var(--paper-raised)",
    border: "1.5px solid var(--line)",
    borderBottom: "none",
    borderRadius: "4px 4px 0 0",
    padding: "36px 40px 28px",
    textAlign: "left",
  },
  eyebrow: {
    fontSize: 12.5,
    color: "var(--gold)",
    fontWeight: 600,
    margin: "0 0 10px",
  },
  wordmark: {
    fontSize: 34,
    margin: "0 0 10px",
  },
  tagline: {
    color: "var(--ink-soft)",
    margin: 0,
    fontSize: 14.5,
  },
  formWrap: {
    maxWidth: 420,
    width: "100%",
    background: "var(--paper-raised)",
    border: "1.5px solid var(--line)",
    borderTop: "none",
    borderRadius: "0 0 4px 4px",
    padding: "28px 40px 40px",
  },
  tabs: {
    display: "flex",
    gap: 4,
    marginBottom: 22,
    borderBottom: "1.5px solid var(--line)",
  },
  tab: {
    flex: 1,
    background: "none",
    border: "none",
    padding: "10px 0",
    fontSize: 14,
    fontWeight: 600,
    color: "var(--ink-soft)",
    cursor: "pointer",
    borderBottom: "2px solid transparent",
    marginBottom: -1.5,
  },
  tabActive: {
    color: "var(--ink)",
    borderBottom: "2px solid var(--rust)",
  },
};
