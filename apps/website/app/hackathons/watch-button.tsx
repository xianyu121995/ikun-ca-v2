"use client";

import React, { useState } from "react";

export function WatchButton({ handle, project, eventTitle, eventId, csrf }: { handle: string; project: string; eventTitle: string; eventId: string; csrf: string }) {
  const [state, setState] = useState<"idle" | "pending" | "done" | "error">("idle");
  async function watch() {
    setState("pending");
    try {
      const response = await fetch("/api/hackathons/watches", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": csrf },
        body: JSON.stringify({ handle, project_name: project, event_title: eventTitle, event_id: eventId }),
      });
      setState(response.ok ? "done" : "error");
    } catch {
      setState("error");
    }
  }
  if (state === "done") return <span className="hk-watched">已加入黑客松推文监控</span>;
  return <button type="button" className="hk-watch" disabled={!csrf || state === "pending"} onClick={() => void watch()}>{state === "error" ? "监控未开始，重试" : state === "pending" ? "提交中" : "监控"}</button>;
}
