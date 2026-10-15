"use client";
import { useEffect, useRef, useState } from "react";
import { TrackingPage } from "./tracking-page";
import { createDemoData } from "./demo-data";
import { validateAccount, type AccountInput } from "./model";

export function FinalTrackingDemo() {
  const [data, setData] = useState<ReturnType<typeof createDemoData> | null>(null);
  const nextLocalKey = useRef(11);
  useEffect(() => { setData(createDemoData(Date.now())); }, []);
  async function onAdd(input: AccountInput) {
    if (!data || validateAccount(input, data.accounts)) throw new Error("Invalid demo input");
    // Explicitly local UI keys. No canonical ID, account lookup or monitor is created.
    const account = { ...input, ui_key: `demo-local-${nextLocalKey.current++}`, avatar: input.name.slice(0, 1), status: "running" as const };
    setData(old => old ? { ...old, accounts: [...old.accounts, account] } : old);
  }
  async function onRemove(key: string) { setData(old => old ? { ...old, accounts: old.accounts.filter(account => account.ui_key !== key) } : old); }
  return <TrackingPage mode="demo" accounts={data?.accounts ?? []} posts={data?.posts ?? []} loading={!data} onAdd={onAdd} onRemove={onRemove} />;
}
