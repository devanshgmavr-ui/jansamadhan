import { useEffect, useState } from "react";
import { Alert, Field } from "../components/ui";
import { govAnalyticsApi } from "../services/govApi";

export function Settings() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    govAnalyticsApi.settings().then((d) => setItems(d.items ?? [])).catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
  }, []);

  const save = async (key, value) => {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await govAnalyticsApi.updateSetting(key, value);
      setNotice(`Saved ${key}.`);
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h2>System Settings</h2>
      <p className="muted">
        Runtime configuration without code edits. Empty values fall back to
        environment defaults. Never enter real secrets into chat or logs.
      </p>
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert>{error}</Alert>}
      {items.map((s) => (
        <SettingRow key={s.key} setting={s} busy={busy} onSave={save} />
      ))}
      {items.length === 0 && !error && <p>Loading...</p>}
    </>
  );
}

function SettingRow({ setting, busy, onSave }) {
  const [value, setValue] = useState(null);
  const shown = value === null ? setting.value : value;
  const secret = setting.key.includes("KEY");
  return (
    <div className="card">
      <p><strong>{setting.key}</strong> {setting.customized && <span className="badge">customized</span>}</p>
      <p className="muted">{setting.purpose} (default: {setting.default || "—"})</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(setting.key, shown);
          setValue(null);
        }}
      >
        <Field label={secret ? "Value (secret — stored server-side)" : "Value"}>
          <input
            type={secret ? "password" : "text"}
            value={shown}
            autoComplete="off"
            onChange={(e) => setValue(e.target.value)}
          />
        </Field>
        <button className="btn secondary" disabled={busy} type="submit">
          Save
        </button>
      </form>
    </div>
  );
}
