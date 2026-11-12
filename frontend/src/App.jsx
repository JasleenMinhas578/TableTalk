import { useCallback, useEffect, useState } from "react";
import { FlaskConical, Home, MessageSquareText, Network, PanelLeft } from "lucide-react";
import { toast } from "sonner";

import { api } from "./api.js";
import { forgetSession, getRecent, rememberSession } from "./lib/storage.js";
import Chat from "./components/Chat.jsx";
import ErMap from "./components/ErMap.jsx";
import Mascot from "./components/Mascot.jsx";
import Playground from "./components/Playground.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Upload from "./components/Upload.jsx";

const TABS = [
  { id: "ask", label: "Ask", icon: MessageSquareText },
  { id: "map", label: "Data map", icon: Network },
  { id: "play", label: "Playground", icon: FlaskConical },
];

// ---------- routes ----------
// "/"                      upload page
// "/s/<id>"                a session, Ask tab
// "/s/<id>/map"            Data map tab
// "/s/<id>/playground"     Playground tab
const TAB_PATHS = { ask: "", map: "/map", play: "/playground" };

function parsePath(pathname) {
  const m = pathname.match(/^\/s\/([0-9a-f]{32})(?:\/(map|playground))?\/?$/);
  if (!m) return { sessionId: null, tab: "ask" };
  return { sessionId: m[1], tab: m[2] === "map" ? "map" : m[2] === "playground" ? "play" : "ask" };
}

function pathFor(sessionId, tab = "ask") {
  return sessionId ? `/s/${sessionId}${TAB_PATHS[tab]}` : "/";
}

export default function App() {
  const [route, setRoute] = useState(() => parsePath(window.location.pathname));
  const [session, setSession] = useState(null); // { id, name, tableCount }
  const [schema, setSchema] = useState(null);
  const [chats, setChats] = useState({}); // chat history per session, kept while the page is open
  const [sql, setSql] = useState("");
  const [showTables, setShowTables] = useState(false);

  // Change the URL (adds a browser history entry, so Back works) and update the screen
  const navigate = useCallback((sessionId, tab = "ask", { replace = false } = {}) => {
    const path = pathFor(sessionId, tab);
    if (path !== window.location.pathname) {
      window.history[replace ? "replaceState" : "pushState"](null, "", path);
    }
    setRoute({ sessionId, tab });
    setShowTables(false);
  }, []);

  // Browser Back / Forward buttons
  useEffect(() => {
    const onPop = () => setRoute(parsePath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // When the session in the URL changes, load its tables
  useEffect(() => {
    const id = route.sessionId;
    if (!id) {
      setSession(null);
      return;
    }
    if (session?.id === id) return;

    const known = getRecent().find((s) => s.id === id);
    setSession(known || { id, name: "Your data", tableCount: 0 });
    setSchema(null);
    setSql("");

    let cancelled = false;
    api
      .schema(id)
      .then((s) => {
        if (cancelled) return;
        setSchema(s);
        rememberSession({ id, name: known?.name || "Your data", tableCount: Object.keys(s.tables).length });
      })
      .catch((e) => {
        if (cancelled) return;
        if (e.status === 404 || e.status === 400) {
          forgetSession(id);
          toast.error("That session no longer exists. Upload the files again.");
          navigate(null, "ask", { replace: true });
        } else {
          toast.error(e.message);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route.sessionId]);

  function open(s) {
    rememberSession(s); // saves the name, so the route effect below can show it
    navigate(s.id, "ask");
  }

  function openInPlayground(code) {
    setSql(code);
    navigate(route.sessionId, "play");
  }

  const tab = route.tab;
  const id = session?.id;
  const messages = (id && chats[id]) || [];
  const setMessages = (update) =>
    setChats((all) => ({ ...all, [id]: typeof update === "function" ? update(all[id] || []) : update }));

  const brand = (
    <a
      className="brand"
      href="/"
      onClick={(e) => {
        e.preventDefault();
        navigate(null);
      }}
    >
      <Mascot size={32} />
      <span>TableTalk</span>
    </a>
  );

  if (!route.sessionId) {
    return (
      <div className="app app--landing">
        <header className="topbar">{brand}</header>
        <Upload onReady={open} />
      </div>
    );
  }

  if (!session) {
    return (
      <div className="app app--landing">
        <header className="topbar">{brand}</header>
        <p className="panel-empty">Opening your data…</p>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="topbar">
        {brand}
        <div className="session-pill" title={session.id}>
          <span className="session-pill__name">{session.name}</span>
          <span className="session-pill__meta">
            {schema ? Object.keys(schema.tables).length : session.tableCount} tables
          </span>
        </div>
        <div className="topbar__actions">
          <button
            className="btn btn--ghost show-md"
            aria-expanded={showTables}
            onClick={() => setShowTables((v) => !v)}
          >
            <PanelLeft size={16} aria-hidden="true" /> Tables
          </button>
          <button className="btn btn--ghost" onClick={() => navigate(null)}>
            <Home size={16} aria-hidden="true" /> Home
          </button>
        </div>
      </header>

      <div className="workspace">
        <div className={`sidebar-wrap ${showTables ? "sidebar-wrap--open" : ""}`}>
          <Sidebar
            key={session.id}
            schema={schema}
            onPreview={(t) => openInPlayground(`SELECT *\nFROM ${t}\nLIMIT 20`)}
          />
        </div>

        <main className="main">
          <nav className="tabs" role="tablist" aria-label="Workspace">
            {TABS.map(({ id: tabId, label, icon: Icon }) => (
              <a
                key={tabId}
                href={pathFor(session.id, tabId)}
                role="tab"
                aria-selected={tab === tabId}
                className={`tab tab--${tabId}`}
                onClick={(e) => {
                  e.preventDefault();
                  navigate(session.id, tabId);
                }}
              >
                <Icon size={16} aria-hidden="true" />
                {label}
              </a>
            ))}
          </nav>

          <div className="panel" role="tabpanel">
            {/* Chat and playground stay mounted so switching tabs keeps their state */}
            <div className="panel__view" hidden={tab !== "ask"}>
              <Chat
                key={session.id}
                sessionId={session.id}
                schema={schema}
                messages={messages}
                setMessages={setMessages}
                onOpenInPlayground={openInPlayground}
              />
            </div>
            {tab === "map" && <ErMap key={session.id} schema={schema} />}
            <div className="panel__view" hidden={tab !== "play"}>
              <Playground key={session.id} sessionId={session.id} schema={schema} sql={sql} setSql={setSql} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
