import { Fragment, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, type Answer, type User } from "../api";

interface Turn {
  question: string;
  answer?: Answer;
  error?: string;
}

const SUGGESTIONS = [
  "How many days of annual leave do I get?",
  "What are the salary bands for senior engineers?",
  "How do I fail over the database?",
];

function withCitations(text: string, sourceCount: number): ReactNode[] {
  return text.split(/(\[\d+\])/g).map((part, i) => {
    const match = /^\[(\d+)\]$/.exec(part);
    if (match && Number(match[1]) <= sourceCount) {
      return (
        <sup key={i} className="cite">
          {match[1]}
        </sup>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export default function Chat({ user }: { user: User }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setTurns((t) => [...t, { question: q }]);
    let update: Partial<Turn>;
    try {
      update = { answer: await api.ask(q) };
    } catch (err) {
      update = { error: (err as Error).message };
    }
    setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, ...update } : turn)));
    setBusy(false);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    void ask(question);
  }

  return (
    <div className="chat">
      <div className="thread">
        {turns.length === 0 && (
          <div className="empty">
            <h2>Ask about company documents</h2>
            <p className="muted">
              {user.roles.length
                ? `You can see documents shared with: ${user.roles.map((r) => r.name).join(", ")}.`
                : "You have no roles yet, so there is nothing to search. Ask an admin for access."}
            </p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => void ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, i) => (
          <div key={i} className="turn">
            <div className="bubble question">{turn.question}</div>
            {turn.error && <div className="bubble answer error">{turn.error}</div>}
            {!turn.answer && !turn.error && <div className="bubble answer pending">Searching…</div>}
            {turn.answer && (
              <div className={`bubble answer ${turn.answer.refused ? "refused" : ""}`}>
                <p>{withCitations(turn.answer.answer, turn.answer.sources.length)}</p>
                {turn.answer.sources.length > 0 && (
                  <ol className="sources">
                    {turn.answer.sources.map((s) => (
                      <li key={s.id}>
                        <span className="cite">{s.id}</span>
                        <strong>{s.title}</strong>
                        <span className="muted">
                          chunk {s.chunk_index} · similarity {s.similarity.toFixed(2)}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          maxLength={2000}
          aria-label="Question"
        />
        <button className="primary" disabled={busy || !question.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
