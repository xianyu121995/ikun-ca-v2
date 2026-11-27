"use client";

import React, { useState } from "react";

export function RemoveWatch({ id, csrf, initial = "idle" }: { id: string; csrf: string; initial?: "idle" | "confirm" }) {
  const [state, setState] = useState<"idle" | "confirm" | "pending" | "done" | "error">(initial);
  async function remove() {
    setState("pending");
    try {
      const response = await fetch(`/api/hackathons/watches/${id}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: { "content-type": "application/json", "x-csrf-token": csrf },
      });
      if (!response.ok) { setState("error"); return; }
      setState("done");
      location.reload();
    } catch {
      setState("error");
    }
  }
  if (state === "confirm" || state === "error") return <span className="hk-row-links">
    <button type="button" className="hk-watch hk-watch-stop" onClick={() => void remove()}>{state === "error" ? "删除失败，重试" : "确认删除"}</button>
    <button type="button" className="hk-watch" onClick={() => setState("idle")}>取消</button>
  </span>;
  return <button type="button" className="hk-watch hk-watch-stop" disabled={state === "pending" || state === "done"} onClick={() => setState("confirm")}>{state === "pending" ? "提交中" : "删除"}</button>;
}
