import { useEffect, useState } from "react";
import { api } from "../api";

function highlight(text: string, excerpt: string | null) {
  if (!excerpt) return [text];
  const words = excerpt.trim().split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(words.join("[\\s\\-]+"), "i");
  const m = re.exec(text);
  if (!m) return [text];
  return [text.slice(0, m.index), <mark key="m">{m[0]}</mark>, text.slice(m.index + m[0].length)];
}

export default function PageViewer({ documentId, page, excerpt, onClose }: {
  documentId: number; page: number; excerpt: string | null; onClose: () => void;
}) {
  const [text, setText] = useState<string | null>(null);
  const [p, setP] = useState(page);
  useEffect(() => {
    setText(null);
    api.get<{ text: string }>(`/api/documents/${documentId}/pages/${p}`).then((r) => setText(r.text)).catch((e) => setText(`Error: ${e.message}`));
  }, [documentId, p]);
  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="panel" style={{ margin: 0, border: 0 }}>
          <h2>
            Official statement · page {p}
            <span className="spacer" />
            <button className="btn" onClick={() => setP(Math.max(1, p - 1))}>‹ Prev</button>
            <button className="btn" onClick={() => setP(p + 1)}>Next ›</button>
            <a className="btn" href={`/api/documents/${documentId}/file#page=${p}`} target="_blank" rel="noreferrer">Open PDF</a>
            <button className="btn" onClick={onClose}>Close</button>
          </h2>
          <div className="body">
            {excerpt && p === page && <div className="muted" style={{ marginBottom: 6 }}>Cited excerpt highlighted.</div>}
            <div className="pageview">{text === null ? "Loading…" : p === page ? highlight(text, excerpt) : text}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
