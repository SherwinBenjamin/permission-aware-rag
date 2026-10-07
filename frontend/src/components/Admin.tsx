import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, type DocumentInfo, type LogPage, type Role, type User } from "../api";

type Tab = "documents" | "users" | "roles" | "logs";
const PAGE_SIZE = 25;

function RolePicker({
  roles,
  selected,
  onToggle,
}: {
  roles: Role[];
  selected: number[];
  onToggle: (id: number) => void;
}) {
  if (!roles.length) return <span className="muted">Create a role first</span>;
  return (
    <div className="role-picker">
      {roles.map((r) => (
        <label key={r.id} className={`toggle ${selected.includes(r.id) ? "on" : ""}`}>
          <input
            type="checkbox"
            checked={selected.includes(r.id)}
            onChange={() => onToggle(r.id)}
          />
          {r.name}
        </label>
      ))}
    </div>
  );
}

function toggled(ids: number[], id: number): number[] {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
}

function Documents({ roles, onError }: { roles: Role[]; onError: (msg: string) => void }) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [roleIds, setRoleIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [formKey, setFormKey] = useState(0);

  const load = useCallback(
    () =>
      api
        .documents()
        .then(setDocs)
        .catch((e) => onError(e.message)),
    [onError],
  );
  useEffect(() => {
    void load();
  }, [load]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    if (title.trim()) form.append("title", title.trim());
    roleIds.forEach((id) => form.append("role_ids", String(id)));
    setBusy(true);
    try {
      await api.uploadDocument(form);
      setFile(null);
      setTitle("");
      setRoleIds([]);
      setFormKey((k) => k + 1);
      await load();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleRole(doc: DocumentInfo, roleId: number) {
    try {
      const updated = await api.setDocumentRoles(
        doc.id,
        toggled(
          doc.roles.map((r) => r.id),
          roleId,
        ),
      );
      setDocs((ds) => ds.map((d) => (d.id === doc.id ? updated : d)));
    } catch (err) {
      onError((err as Error).message);
    }
  }

  async function remove(doc: DocumentInfo) {
    if (!confirm(`Delete "${doc.title}" and all its chunks?`)) return;
    try {
      await api.deleteDocument(doc.id);
      setDocs((ds) => ds.filter((d) => d.id !== doc.id));
    } catch (err) {
      onError((err as Error).message);
    }
  }

  return (
    <>
      <form key={formKey} className="card upload" onSubmit={upload}>
        <h3>Upload a document</h3>
        <div className="upload-row">
          <input
            type="file"
            accept=".pdf,.md,.markdown,.txt"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required
          />
          <input
            placeholder="Title (defaults to file name)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div className="field-label">Visible to</div>
        <RolePicker
          roles={roles}
          selected={roleIds}
          onToggle={(id) => setRoleIds((ids) => toggled(ids, id))}
        />
        <button className="primary" disabled={busy || !file}>
          {busy ? "Ingesting…" : "Upload"}
        </button>
      </form>

      <table>
        <thead>
          <tr>
            <th>Document</th>
            <th>Visible to</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {docs.map((doc) => (
            <tr key={doc.id}>
              <td>
                <strong>{doc.title}</strong>
                <div className="muted small">
                  {doc.filename} · {new Date(doc.created_at).toLocaleDateString()}
                </div>
              </td>
              <td>
                <RolePicker
                  roles={roles}
                  selected={doc.roles.map((r) => r.id)}
                  onToggle={(id) => void toggleRole(doc, id)}
                />
                {doc.roles.length === 0 && <div className="warn small">Hidden from everyone</div>}
              </td>
              <td className="right">
                <button className="danger" onClick={() => void remove(doc)}>
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {docs.length === 0 && (
            <tr>
              <td colSpan={3} className="muted">
                No documents yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}

function Users({
  roles,
  onError,
  onChange,
}: {
  roles: Role[];
  onError: (msg: string) => void;
  onChange: () => void;
}) {
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    api
      .users()
      .then(setUsers)
      .catch((e) => onError(e.message));
  }, [onError]);

  async function toggleRole(user: User, roleId: number) {
    try {
      const updated = await api.setUserRoles(
        user.id,
        toggled(
          user.roles.map((r) => r.id),
          roleId,
        ),
      );
      setUsers((us) => us.map((u) => (u.id === user.id ? updated : u)));
      onChange();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  return (
    <table>
      <thead>
        <tr>
          <th>User</th>
          <th>Roles</th>
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.id}>
            <td>
              {u.email} {u.is_admin && <span className="chip">admin</span>}
            </td>
            <td>
              <RolePicker
                roles={roles}
                selected={u.roles.map((r) => r.id)}
                onToggle={(id) => void toggleRole(u, id)}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Roles({
  roles,
  onCreated,
  onError,
}: {
  roles: Role[];
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const [name, setName] = useState("");

  async function create(e: FormEvent) {
    e.preventDefault();
    try {
      await api.createRole(name.trim().toLowerCase());
      setName("");
      onCreated();
    } catch (err) {
      onError((err as Error).message);
    }
  }

  return (
    <div className="card">
      <form className="inline" onSubmit={create}>
        <input
          placeholder="new-role"
          value={name}
          pattern="[a-z0-9][a-z0-9_\-]*"
          title="Lowercase letters, digits, - and _"
          onChange={(e) => setName(e.target.value)}
          required
        />
        <button className="primary">Create role</button>
      </form>
      <div className="role-list spaced">
        {roles.map((r) => (
          <span key={r.id} className="chip">
            {r.name}
          </span>
        ))}
      </div>
    </div>
  );
}

function Logs({ onError }: { onError: (msg: string) => void }) {
  const [page, setPage] = useState<LogPage>({ total: 0, items: [] });
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    api
      .logs(PAGE_SIZE, offset)
      .then(setPage)
      .catch((e) => onError(e.message));
  }, [offset, onError]);

  return (
    <>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>Question</th>
            <th>Retrieved documents</th>
          </tr>
        </thead>
        <tbody>
          {page.items.map((log) => (
            <tr key={log.id}>
              <td className="nowrap small">{new Date(log.created_at).toLocaleString()}</td>
              <td>{log.user_email ?? <span className="muted">deleted user</span>}</td>
              <td>{log.question}</td>
              <td>
                {log.refused ? (
                  <span className="chip muted">refused</span>
                ) : (
                  log.retrieved_titles.map((t, i) => (
                    <span key={i} className="chip">
                      {t}
                    </span>
                  ))
                )}
              </td>
            </tr>
          ))}
          {page.items.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No questions asked yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      <div className="pager">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Newer
        </button>
        <span className="muted small">
          {page.total
            ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, page.total)} of ${page.total}`
            : "0 entries"}
        </span>
        <button
          disabled={offset + PAGE_SIZE >= page.total}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Older
        </button>
      </div>
    </>
  );
}

export default function Admin({ onChange }: { onChange: () => void }) {
  const [tab, setTab] = useState<Tab>("documents");
  const [roles, setRoles] = useState<Role[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadRoles = useCallback(() => {
    api
      .roles()
      .then(setRoles)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(loadRoles, [loadRoles]);

  const tabs: [Tab, string][] = [
    ["documents", "Documents"],
    ["users", "Users"],
    ["roles", "Roles"],
    ["logs", "Audit log"],
  ];

  return (
    <div className="admin">
      <nav className="subtabs">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            onClick={() => {
              setTab(key);
              setError(null);
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      {error && (
        <p className="error" onClick={() => setError(null)}>
          {error}
        </p>
      )}
      {tab === "documents" && <Documents roles={roles} onError={setError} />}
      {tab === "users" && <Users roles={roles} onError={setError} onChange={onChange} />}
      {tab === "roles" && <Roles roles={roles} onCreated={loadRoles} onError={setError} />}
      {tab === "logs" && <Logs onError={setError} />}
    </div>
  );
}
