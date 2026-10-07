import { useState, type FormEvent } from "react";
import { api } from "../api";

interface Props {
  notice: string | null;
  onSignedIn: (token: string) => void;
}

export default function AuthScreen({ notice, onSignedIn }: Props) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "register") await api.register(email, password);
      const { access_token } = await api.login(email, password);
      onSignedIn(access_token);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <form className="card auth-card" onSubmit={submit}>
        <h1>Permission-Aware RAG</h1>
        <p className="muted">Answers come only from documents your roles can see.</p>
        {notice && <p className="notice">{notice}</p>}
        <label>
          Email
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            minLength={mode === "register" ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="primary" disabled={busy}>
          {mode === "login" ? "Sign in" : "Create account"}
        </button>
        <p className="muted small">
          {mode === "login" ? "No account yet?" : "Already registered?"}{" "}
          <button
            type="button"
            className="link"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "Register" : "Sign in"}
          </button>
        </p>
        {mode === "register" && (
          <p className="muted small">New accounts have no roles until an admin assigns them.</p>
        )}
      </form>
    </div>
  );
}
