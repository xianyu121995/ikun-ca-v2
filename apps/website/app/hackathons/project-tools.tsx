"use client";

import React, { useEffect, useState } from "react";
import { beijingLabel, projectKey, type StoredAnalysis, type StoredNote } from "../../lib/hackathon-watch-model";
import { WatchButton } from "./watch-button";

const listeners = new Set<(id: string | null) => void>();
let selectedId: string | null = null;

function selectProject(id: string | null) {
  selectedId = id;
  for (const listener of listeners) listener(id);
}

export function ProjectTools({ eventId, eventTitle, role, name, csrf, place, info, website, handle, twitter, sourceUrl, note, analysis, initialOpen = false }: {
  eventId: string;
  eventTitle: string;
  role: string;
  name: string;
  csrf: string;
  place: string;
  info: string;
  website: string;
  handle: string;
  twitter: string;
  sourceUrl: string;
  note?: StoredNote;
  analysis?: StoredAnalysis;
  initialOpen?: boolean;
}) {
  const key = projectKey(eventId, role, name);
  const [selected, setSelected] = useState<string | null>(initialOpen ? key : selectedId);
  const [draft, setDraft] = useState(note?.text ?? "");
  const [saved, setSaved] = useState(note);
  const [current, setCurrent] = useState(analysis);
  const [pending, setPending] = useState<"note" | "analysis" | "">("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (initialOpen) selectProject(key);
    listeners.add(setSelected);
    setSelected(selectedId);
    return () => { listeners.delete(setSelected); };
  }, [initialOpen, key]);

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
    } catch {
      setError("备注没有保存");
    } finally {
      setPending("");
    }
  }

  async function generate() {
    setPending("analysis");
    setError("");
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

  const open = selected === key;
  return <>
    <button type="button" className="hk-project-name" onClick={() => selectProject(key)}>{name}</button>
    <button type="button" className="hk-watch" onClick={() => selectProject(key)}>资料</button>
    {open && <aside className="hk-drawer" aria-label="项目资料">
      <button type="button" className="hk-drawer-back" onClick={() => selectProject(null)}>← 收起资料</button>
      <div className="hk-drawer-scroll">
        <div className="hk-drawer-identity">
          <span className="hk-drawer-avatar" aria-hidden="true">{Array.from(name)[0] || "?"}</span>
          <div>
            <h2>{name}</h2>
            <p>{handle ? `@${handle}` : "来源没有官推"}{place ? ` · 排名 ${place}` : ""}</p>
          </div>
        </div>
        <p className="hk-drawer-kicker">项目资料</p>
        <label className="hk-field">官方简介<textarea readOnly rows={3} value={info || "来源没有写出简介。"} /></label>
        <label className="hk-field">官网<input readOnly value={website || "来源没有写出官网。"} /></label>
        <label className="hk-field">官推<input readOnly value={handle ? `@${handle}` : "来源没有写出官推。"} /></label>
        {handle && <p className="hk-row-links"><a href={twitter}>@{handle} 官推</a><WatchButton handle={handle} project={name} eventTitle={eventTitle} eventId={eventId} csrf={csrf} /></p>}
        {place && <label className="hk-field">排名<input readOnly value={place} /></label>}
        {sourceUrl && <p className="hk-row-links"><a href={sourceUrl}>来源</a></p>}
        <label className="hk-field">备注<textarea value={draft} maxLength={2000} onChange={event => setDraft(event.target.value)} /></label>
        <p className="hk-row-links"><button type="button" className="hk-watch" disabled={!csrf || pending === "note"} onClick={() => void saveNote()}>{pending === "note" ? "保存中" : "保存备注"}</button>{saved?.updated_at ? <span className="hk-note">已保存 {beijingLabel(saved.updated_at)}</span> : <span className="hk-note">备注只存在这一届黑客松的记录里。</span>}</p>
        <label className="hk-field">AI 分析<textarea readOnly rows={5} value={current?.text || "还没有分析。生成时只使用官方字段，以及监控开始后已经保存的官推。"} /></label>
        <p className="hk-row-links">
          <button type="button" className="hk-watch" disabled={!csrf || pending === "analysis"} onClick={() => void generate()}>{pending === "analysis" ? "生成中" : current ? "重新生成" : "生成分析"}</button>
          {current && <span className="hk-note">生成于 {beijingLabel(current.generated_at)}</span>}
        </p>
        {error && <p className="hk-note">{error}</p>}
      </div>
    </aside>}
  </>;
}
