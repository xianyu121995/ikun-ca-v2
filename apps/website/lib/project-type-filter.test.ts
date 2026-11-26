import assert from "node:assert/strict";
import { test } from "node:test";
import { PROJECT_TYPES } from "../features/homepage/reference-model";
import { applyCategoryRatings, collectProjectTypes, handlesByProjectId, indexProjectRecords, recordsFromListItems, resolveProjectCategory } from "./project-type-filter";

const rated = (project_id: string, rating: string | null, state = "found") => ({ project_id, state, rating, revision: state === "found" ? 3 : null });

test("homepage list items and flat rows index by project id and handle", () => {
  const records = recordsFromListItems([
    { project: { project_id: "prj_nft", category: "NFT", x_handle: "@Alpha" } },
    { project_id: "prj_blank", category: "", x_handle: "plain" },
    { project: { project_id: "prj_game", category: "链游", x_handle: null } },
    { nope: true },
  ]);
  const index = indexProjectRecords(records);
  assert.equal(index.byId.get("prj_nft"), "NFT");
  assert.equal(index.byId.get("prj_blank"), null);
  assert.equal(index.byHandle.get("alpha"), "NFT");
  assert.equal(index.byHandle.get("plain"), null);
  assert.equal(resolveProjectCategory(index, { projectId: "prj_game" }), "链游");
  assert.equal(resolveProjectCategory(index, { projectId: "missing", handle: "@Alpha" }), "NFT");
  assert.equal(resolveProjectCategory(index, { projectId: "prj_blank", handle: "@Alpha" }), null);
  assert.equal(resolveProjectCategory(index, { projectId: "missing", handle: "@nobody" }), null);
});

test("type filter nulls other projects and keeps ids, including 未分类", () => {
  const index = indexProjectRecords([
    { project_id: "nft", category: "NFT", x_handle: "nft_handle" },
    { project_id: "launch", category: "发射台" },
    { project_id: "blank", category: "" },
  ]);
  const items = [rated("nft", "S"), rated("launch", "A"), rated("blank", "B"), rated("orphan", "S"), rated("gone", null, "missing")];
  const categoryOf = (id: string) => resolveProjectCategory(index, { projectId: id, handle: id === "orphan" ? "nft_handle" : null });
  const nft = applyCategoryRatings(items, categoryOf, "NFT");
  assert.deepEqual(nft.map(item => item.project_id), items.map(item => item.project_id));
  assert.deepEqual(nft.map(item => item.rating), ["S", null, null, "S", null]);
  assert.equal(nft[1]!.revision, 3);
  assert.equal(nft[4]!.state, "missing");
  const none = applyCategoryRatings(items, categoryOf, "none");
  assert.deepEqual(none.map(item => item.rating), [null, null, "B", null, null]);
  assert.deepEqual(applyCategoryRatings(items, categoryOf, "all").map(item => item.rating), ["S", "A", "B", "S", null]);
  assert.ok(PROJECT_TYPES.includes("撸毛"));
});

test("catalog paging covers hidden projects and refuses a stuck cursor", async () => {
  const pages: Record<string, { items: unknown[]; next_cursor: string | null }[]> = {
    active: [{ items: [{ project: { project_id: "a", category: "NFT", x_handle: "aaa" } }], next_cursor: "c1" }, { items: [{ project_id: "b", category: "链游", x_handle: "bbb" }], next_cursor: null }],
    hidden: [{ items: [{ project: { project_id: "h", category: null, x_handle: "hid" } }], next_cursor: null }],
    removed: [{ items: [{ project_id: "r", category: "撸毛", x_handle: "@Removed" }], next_cursor: null }],
  };
  const seen: string[] = [];
  const index = await collectProjectTypes(async (membership, cursor) => {
    seen.push(membership + ":" + cursor);
    const batch = pages[membership]!.shift();
    if (!batch) throw Error("extra page");
    return batch;
  });
  assert.deepEqual(seen, ["active:null", "active:c1", "hidden:null", "removed:null"]);
  assert.equal(index.byId.get("h"), null);
  assert.equal(index.byHandle.get("removed"), "撸毛");
  await assert.rejects(collectProjectTypes(async () => ({ items: [], next_cursor: "loop" })), /UPSTREAM/);
});

test("handle lookup stops once every missing project id is found", async () => {
  const calls: (string | null)[] = [];
  const handles = await handlesByProjectId(async cursor => {
    calls.push(cursor);
    return cursor ? { items: [{ project_id: "b", x_handle: "bee" }], next_cursor: "more" } : { items: [{ project_id: "a", x_handle: "@Aye" }], next_cursor: "next" };
  }, new Set(["a", "b"]));
  assert.equal(handles.get("a"), "@Aye");
  assert.equal(handles.get("b"), "bee");
  assert.deepEqual(calls, [null, "next"]);
});
