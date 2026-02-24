import { useEffect, useMemo, useState } from "react";

const API_BASE = "/api/v1";

async function fetchJson(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${text}`);
  }
  return res.json();
}

function Section({ title, children }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function JsonView({ value }) {
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [profiles, setProfiles] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [traffic, setTraffic] = useState([]);
  const [stateDump, setStateDump] = useState({});
  const [capabilities, setCapabilities] = useState([]);
  const [activeProfile, setActiveProfile] = useState("atlas_pf");
  const [eventName, setEventName] = useState("tightening");
  const [eventPayload, setEventPayload] = useState('{"torque_nm": 12.3, "angle_deg": 123}');
  const [scenarioName, setScenarioName] = useState("tightening_burst");
  const [scenarioList, setScenarioList] = useState([]);
  const [error, setError] = useState("");

  const summary = useMemo(() => {
    if (!health) return "Loading...";
    return `Profile ${health.profile} | MIDs ${health.mid_count} | Sessions ${health.sessions}`;
  }, [health]);

  async function refresh() {
    try {
      const [h, p, s, t, st, c, sc] = await Promise.all([
        fetchJson("/health"),
        fetchJson("/profiles"),
        fetchJson("/sessions"),
        fetchJson("/traffic?limit=50"),
        fetchJson("/state"),
        fetchJson("/capabilities"),
        fetchJson("/scenarios")
      ]);
      setHealth(h);
      setProfiles(p);
      setSessions(s);
      setTraffic(t);
      setStateDump(st);
      setCapabilities(c.items || []);
      setScenarioList(sc.scenarios || []);
      setActiveProfile(p.active);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, []);

  async function switchProfile(e) {
    const profile = e.target.value;
    setActiveProfile(profile);
    try {
      await fetchJson("/profiles/active", {
        method: "PUT",
        body: JSON.stringify({ profile })
      });
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  async function injectEvent() {
    try {
      const payload = JSON.parse(eventPayload || "{}");
      await fetchJson(`/events/${eventName}`, {
        method: "POST",
        body: JSON.stringify({ payload })
      });
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  async function runScenario() {
    try {
      await fetchJson("/scenarios/run", {
        method: "POST",
        body: JSON.stringify({ name: scenarioName, payload: {} })
      });
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  async function resetSimulator() {
    try {
      await fetchJson("/reset", { method: "POST", body: "{}" });
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="app">
      <header className="hero">
        <h1>OpenProtocol Torque Simulator</h1>
        <p>{summary}</p>
      </header>

      <div className="toolbar">
        <label>
          Active Profile
          <select value={activeProfile} onChange={switchProfile}>
            {(profiles?.profiles || []).map((p) => (
              <option key={p.name} value={p.name}>
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
        <button onClick={resetSimulator}>Reset</button>
        <button onClick={refresh}>Refresh</button>
      </div>

      {error && <div className="error">Error: {error}</div>}

      <div className="grid">
        <Section title="Health">
          <JsonView value={health || {}} />
        </Section>

        <Section title="Sessions">
          <table>
            <thead>
              <tr>
                <th>Session</th>
                <th>Role</th>
                <th>Ack</th>
                <th>Started</th>
                <th>Subscriptions</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.session_id}>
                  <td>{s.session_id}</td>
                  <td>{s.role}</td>
                  <td>{s.ack_mode}</td>
                  <td>{String(s.communication_started)}</td>
                  <td>{(s.subscriptions || []).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Event Injection">
          <div className="form">
            <label>
              Event
              <select value={eventName} onChange={(e) => setEventName(e.target.value)}>
                <option value="tightening">tightening</option>
                <option value="alarm">alarm</option>
                <option value="io_change">io_change</option>
                <option value="trace">trace</option>
              </select>
            </label>
            <label>
              Payload JSON
              <textarea value={eventPayload} onChange={(e) => setEventPayload(e.target.value)} rows={6} />
            </label>
            <button onClick={injectEvent}>Inject Event</button>
          </div>
        </Section>

        <Section title="Scenario Runner">
          <div className="form">
            <label>
              Scenario
              <select value={scenarioName} onChange={(e) => setScenarioName(e.target.value)}>
                {scenarioList.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <button onClick={runScenario}>Run Scenario</button>
          </div>
        </Section>

        <Section title="Traffic (latest 50)">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Dir</th>
                <th>MID</th>
                <th>Rev</th>
                <th>Session</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {traffic.map((t, idx) => (
                <tr key={`${t.timestamp}-${idx}`}>
                  <td>{t.timestamp?.slice(11, 19)}</td>
                  <td>{t.direction}</td>
                  <td>{t.mid}</td>
                  <td>{t.revision}</td>
                  <td>{t.session_id}</td>
                  <td>{t.decoded_data}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="State">
          <JsonView value={stateDump} />
        </Section>

        <Section title="Capability Matrix">
          <div className="matrix">
            {capabilities.map((c) => (
              <div key={c.mid} className={`cap ${c.supported ? "ok" : "no"}`}>
                <span className="mid">{c.mid}</span>
                <span className="name">{c.name}</span>
                <span className="revs">rev: {(c.revisions || []).join(",")}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}

