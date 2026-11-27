"use client";

import React, { useState } from "react";
import { beijingLabel, type StoredAnalysis, type StoredNote } from "../../lib/hackathon-watches";

export function ProjectTools({ eventId, role, name, csrf, note, analysis, initialEditing = false, initialOpen = false }: {
  eventId: string;
  role: string;
  name: string;
  csrf: string;
  note?: StoredNote;
  analysis?: StoredAnalysis;
  initialEditing?: boolean;
  initialOpen?: boolean;
}) {
  const [editing, setEditing] = useState(initialEditing);
  const [draft, setDraft] = useState(note?.text ?? "");
  const [saved, setSaved] = useState(note);
  const [open, setOpen] = useState(initialOpen || Boolean(analysis));
  const [current, setCurrent] = useState(analysis);
  const [pending, setPending] = useState<"note" | "analysis" | "">("");
  const [error, setError] = useState("");

  async function saveNote() {
    setPending("note");
    setError("");
    try {
      const response = await fetch("/api/hackathons/notes", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": csrf },
        body: JSON.stringify({ event_id: eventId, role, name, text: draft }),
      });
      const payload = await response.json().catch(() => null) as { data?: { note: StoredNote | null }; error?: { message?: string } } | null;
      if (!response.ok) { setError(payload?.error?.message || "备注没有保存"); return; }
      setSaved(payload?.data?.note ?? undefined);
      setEditing(false);
    } catch {
      setError("备注没有保存");
    } finally {
      setPending("");
    }
  }

  async function generate() {
    setPending("analysis");
    setError("");
    setOpen(true);
    try {
      const response = await fetch("/api/hackathons/analyses", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": csrf },
        body: JSON.stringify({ event_id: eventId, role, name }),
      });
      const payload = await response.json().catch(() => null) as { data?: { analysis: StoredAnalysis }; error?: { message?: string } } | null;
      if (!response.ok || !payload?.data?.analysis) { setError(payload?.error?.message || "没有生成分析"); return; }
      setCurrent(payload.data.analysis);
    } catch {
      setError("没有生成分析");
    } finally {
      setPending("");
    }
  }

  return <div className="hk-tools">
    {editing ? <div className="hk-note-edit">
      <label>备注<textarea value={draft} maxLength={2000} onChange={event => setDraft(event.target.value)} /></label>
      <span className="hk-row-links">
        <button type="button" className="hk-watch" disabled={!csrf || pending === "note"} onClick={() => void saveNote()}>{pending === "note" ? "保存中" : "保存备注"}</button>
        <button type="button" className="hk-watch" onClick={() => { setEditing(false); setDraft(saved?.text ?? ""); }}>取消</button>
      </span>
    </div> : <p className="hk-user-note"><span>备注</span> {saved?.text || "还没有备注"} <button type="button" className="hk-watch" onClick={() => setEditing(true)}>{saved ? "编辑" : "写备注"}</button></p>}
    <details className="hk-analysis" open={open} onToggle={event => setOpen((event.target as HTMLDetailsElement).open)}>
      <summary>AI 分析</summary>
      {current ? <div>
        <p>{current.text}</p>
        <p className="hk-note">只根据官方字段和已保存的官推。生成于 {beijingLabel(current.generated_at)}</p>
      </div> : <p className="hk-note">还没有分析。生成时只使用这个项目的官方字段，以及监控开始后已经保存的官推。</p>}
      <button type="button" className="hk-watch" disabled={!csrf || pending === "analysis"} onClick={() => void generate()}>{pending === "analysis" ? "生成中" : current ? "重新生成" : "生成分析"}</button>
    </details>
    {error && <p className="hk-note">{error}</p>}
  </div>;
}
