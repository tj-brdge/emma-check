import { useEffect, useState } from "react";
import { getUser, setUser } from "./api";
import Queue from "./pages/Queue";
import FindingDetailPage from "./pages/FindingDetail";
import Flags from "./pages/Flags";
import Data from "./pages/Data";
import Audit from "./pages/Audit";
import Guide from "./pages/Guide";

function useHash() {
  const [hash, setHash] = useState(window.location.hash || "#/start");
  useEffect(() => {
    const on = () => setHash(window.location.hash || "#/start");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

export default function App() {
  const hash = useHash();
  const [user, setU] = useState(getUser());
  const parts = hash.replace(/^#\//, "").split("/");
  const section = parts[0] || "start";

  let page;
  if (section === "findings" && parts[1]) page = <FindingDetailPage id={Number(parts[1])} />;
  else if (section === "flags") page = <Flags runId={parts[1] ? Number(parts[1]) : undefined} />;
  else if (section === "data") page = <Data />;
  else if (section === "audit") page = <Audit />;
  else if (section === "start") page = <Guide />;
  else page = <Queue />;

  const tab = (key: string, label: string) => (
    <a href={`#/${key}`} className={section === key || (key === "queue" && section === "findings") ? "active" : ""}>
      {label}
    </a>
  );

  return (
    <>
      <header className="top">
        <div className="brand">TERMS CHECK</div>
        <nav>
          {tab("start", "Start here")}
          {tab("queue", "Review queue")}
          {tab("flags", "Screen flags")}
          {tab("data", "Data & runs")}
          {tab("audit", "Audit trail")}
        </nav>
        <div className="user">
          Reviewer
          <input
            value={user}
            placeholder="your name"
            onChange={(e) => {
              setU(e.target.value);
              setUser(e.target.value);
            }}
          />
        </div>
      </header>
      <main>
        {!user.trim() && <div className="note">Enter your name as reviewer (top right). Every action is logged under it.</div>}
        {page}
      </main>
    </>
  );
}
