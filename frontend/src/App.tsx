import { useCallback, useEffect, useState } from "react";
import { api, getToken, setToken, setUnauthorizedHandler, type User } from "./api";
import Admin from "./components/Admin";
import AuthScreen from "./components/AuthScreen";
import Chat from "./components/Chat";

type View = "ask" | "admin";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(Boolean(getToken()));
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<View>("ask");

  const signOut = useCallback((message?: string) => {
    setToken(null);
    setUser(null);
    setView("ask");
    setNotice(message ?? null);
  }, []);

  const loadMe = useCallback(async () => {
    try {
      setUser(await api.me());
    } catch {
      signOut();
    } finally {
      setLoading(false);
    }
  }, [signOut]);

  useEffect(() => {
    setUnauthorizedHandler(() => signOut("Your session expired. Please sign in again."));
    if (getToken()) void loadMe();
  }, [loadMe, signOut]);

  if (loading) return <div className="splash">Loading…</div>;

  if (!user) {
    return (
      <AuthScreen
        notice={notice}
        onSignedIn={(token) => {
          setToken(token);
          setNotice(null);
          setLoading(true);
          void loadMe();
        }}
      />
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            ◆
          </span>
          Permission-Aware RAG
        </div>
        <nav className="tabs">
          <button className={view === "ask" ? "active" : ""} onClick={() => setView("ask")}>
            Ask
          </button>
          {user.is_admin && (
            <button className={view === "admin" ? "active" : ""} onClick={() => setView("admin")}>
              Admin
            </button>
          )}
        </nav>
        <div className="whoami">
          <span className="email">{user.email}</span>
          <span className="role-list">
            {user.roles.length ? (
              user.roles.map((r) => (
                <span key={r.id} className="chip">
                  {r.name}
                </span>
              ))
            ) : (
              <span className="chip muted">no roles</span>
            )}
          </span>
          <button className="link" onClick={() => signOut()}>
            Sign out
          </button>
        </div>
      </header>
      <main>
        {view === "admin" && user.is_admin ? <Admin onChange={loadMe} /> : <Chat user={user} />}
      </main>
    </div>
  );
}
