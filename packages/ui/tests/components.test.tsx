import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { createRef } from "react";
import { Alert, AppShell, BUSINESS_NAVIGATION, Button, DataTable, Dialog, Input, LoginPanel, ScoreBadge, SearchInput, isNavigationActive } from "../src/index.js";

test("business navigation has exactly three entries and matches complete path segments", () => {
  assert.deepEqual(BUSINESS_NAVIGATION.map(n => n.label), ["主页", "猎手监控", "猎手项目监控"]);
  assert.equal(isNavigationActive("/hunter/signals?sort=time", "/hunter"), true);
  assert.equal(isNavigationActive("/hunter-extra", "/hunter"), false);
  assert.equal(isNavigationActive("/hunter", "/"), false);
  assert.equal(isNavigationActive("/?view=all", "/"), true);
  const html = renderToStaticMarkup(<AppShell pathname="/tracking/abc" account={{ name: "示例" }}>内容</AppShell>);
  assert.equal((html.match(/aria-current="page"/g) ?? []).length, 1);
  assert.match(html, /aria-label="猎手项目监控"/);
  assert.match(html, /href="\/account"/);
});

test("pending button prevents duplicate submission and retains its label", () => {
  const html = renderToStaticMarkup(<Button type="submit" pending>保存</Button>);
  assert.match(html, /disabled=""/); assert.match(html, /aria-busy="true"/); assert.match(html, /保存/);
  assert.match(renderToStaticMarkup(<Button>操作</Button>), /type="button"/);
});

test("fields preserve native labels and link hints and errors", () => {
  const html = renderToStaticMarkup(<Input id="field" label="名称" hint="帮助" error="格式错误" required />);
  assert.match(html, /for="field"/); assert.match(html, /aria-invalid="true"/);
  assert.match(html, /aria-describedby="field-hint field-error"/);
  assert.match(html, /id="field-error"/); assert.match(html, /required=""/);
});

test("search has an accessible label and only shows clear when populated", () => {
  const html = renderToStaticMarkup(<SearchInput label="项目搜索" value="north" onValueChange={() => {}} />);
  assert.match(html, /项目搜索/); assert.match(html, /aria-label="清除项目搜索"/);
  assert.doesNotMatch(renderToStaticMarkup(<SearchInput label="项目搜索" value="" onValueChange={() => {}} />), /aria-label="清除/);
});

test("unknown or invalid score values are never rendered as an inferred zero", () => {
  assert.match(renderToStaticMarkup(<ScoreBadge />), /未评分/);
  for (const value of [NaN, Infinity, -1, 101]) {
    const html = renderToStaticMarkup(<ScoreBadge grade="S" value={value} />);
    assert.match(html, /S 级/); assert.doesNotMatch(html, / 分|NaN|Infinity/);
  }
  assert.match(renderToStaticMarkup(<ScoreBadge grade="A" value={0} />), /A 级，0 分/);
});

const columns = [{ key: "name", header: "名称", sortable: true, render: (r: { id: string; name: string }) => r.name }];
test("table exposes native sorting and retains records while refresh fails", () => {
  const html = renderToStaticMarkup(<DataTable caption="项目" columns={columns} rows={[{ id: "a", name: "保留数据" }]} rowKey={r => r.id} sort={{ key: "name", direction: "asc" }} onSortChange={() => {}} error={<Alert tone="danger" title="刷新失败" />} />);
  assert.match(html, /<table/); assert.match(html, /scope="col"/); assert.match(html, /aria-sort="ascending"/);
  assert.match(html, /保留数据/); assert.match(html, /刷新失败/); assert.doesNotMatch(html, /暂无数据/);
});

test("table separates initial loading, empty state and retained-data refresh", () => {
  const loading = renderToStaticMarkup(<DataTable caption="项目" columns={columns} rows={[]} rowKey={r => r.id} loading />);
  assert.match(loading, /aria-busy="true"/); assert.match(loading, /正在加载项目/); assert.doesNotMatch(loading, /暂无数据/);
  const empty = renderToStaticMarkup(<DataTable caption="项目" columns={columns} rows={[]} rowKey={r => r.id} />);
  assert.match(empty, /暂无数据/);
  const refresh = renderToStaticMarkup(<DataTable caption="项目" columns={columns} rows={[{ id: "a", name: "旧数据" }]} rowKey={r => r.id} refreshing />);
  assert.match(refresh, /旧数据/); assert.match(refresh, /更新中/);
});

test("login supports autofill and disables submit when authentication is unavailable", () => {
  const html = renderToStaticMarkup(<LoginPanel onSubmit={() => {}} disabled error="认证服务未接入" />);
  assert.match(html, /autoComplete="username"/); assert.match(html, /autoComplete="current-password"/);
  assert.match(html, /type="password"/); assert.match(html, /aria-controls=/);
  assert.match(html, /role="alert"/); assert.match(html, /type="submit" disabled=""/);
});

test("dialog is labelled and errors support request IDs without requiring backend details", () => {
  const cancelRef = createRef<HTMLButtonElement>();
  const html = renderToStaticMarkup(<Dialog open={false} onOpenChange={() => {}} initialFocusRef={cancelRef} title="确认操作" description="说明" footer={<Button ref={cancelRef}>取消</Button>}>内容</Dialog>);
  assert.match(html, /<dialog/); assert.match(html, /aria-modal="true"/); assert.match(html, /aria-labelledby=/); assert.match(html, /aria-describedby=/);
  assert.match(renderToStaticMarkup(<Alert tone="danger" title="失败" requestId="request-123" />), /请求编号：request-123/);
});

test("dark theme text and form boundaries meet contrast targets", () => {
  const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
  function token(name: string) { const result = css.match(new RegExp(`--ik-${name}: (#[0-9a-f]{6})`)); assert.ok(result?.[1]); return result[1]; }
  function luminance(hex: string) {
    const [r = 0, g = 0, b = 0] = [1, 3, 5].map(i => { const v = parseInt(hex.slice(i, i + 2), 16) / 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
    return .2126 * r + .7152 * g + .0722 * b;
  }
  function contrast(a: string, b: string) { const x = luminance(token(a)); const y = luminance(token(b)); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); }
  for (const foreground of ["text", "secondary", "muted"]) for (const background of ["bg", "panel", "raised"]) assert.ok(contrast(foreground, background) >= 4.5, `${foreground} on ${background}`);
  for (const background of ["bg", "panel", "raised"]) assert.ok(contrast("control-border", background) >= 3);
  assert.ok(contrast("on-accent", "accent") >= 4.5);
  for (const tone of ["success", "info", "warning", "danger"]) assert.ok(contrast(tone, `${tone}-bg`) >= 4.5);
});
