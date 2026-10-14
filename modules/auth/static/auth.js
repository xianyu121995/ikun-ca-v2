"use strict";
const page = document.body.dataset.page;
let session, dialogAction, dialogUser, dialogKey;
const $ = id => document.getElementById(id);
const roles = {superadmin: "超级管理员", user: "普通用户"};
function message(text, id = "status", success = false) {
  const el = $(id); if (el) { el.textContent = text; el.classList.toggle("success", success); }
}
function safeNext() {
  const raw = new URLSearchParams(location.search).get("next") || "/";
  try {
    const target = new URL(raw, location.origin);
    if (raw.startsWith("/") && target.origin === location.origin &&
        !target.pathname.startsWith("/api/") && target.pathname !== "/login")
      return target.pathname + target.search;
  } catch (_) { /* Fall through to the account page. */ }
  return "/auth";
}
async function api(path, method = "GET", body, extra = {}) {
  const headers = {...extra};
  if (method !== "GET") {
    headers["Content-Type"] = "application/json";
    if (session) headers["X-CSRF-Token"] = session.csrf_token;
  }
  let response;
  try {
    response = await fetch(path, {method, headers, credentials: "same-origin", cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(10000)});
  } catch (_) { throw new Error("连接超时或网络不可用，请稍后重试。"); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && page !== "login") {
      document.querySelector("main")?.replaceChildren();
      location.replace("/login?next=" + encodeURIComponent(location.pathname));
    }
    throw new Error(data.error?.message || "操作失败，请稍后重试。");
  }
  if (["/api/v1/auth/me", "/api/v1/auth/login", "/api/v1/auth/password"].includes(path)) {
    const value = data.data;
    return {user: {id: value.user_id, username: value.username, role: value.role,
      tenant_id: value.tenant_id, must_change_password: value.must_change_password}, csrf_token: value.csrf_token};
  }
  return data.data;
}
async function submit(form, action, status = "status") {
  const button = form.querySelector('[type="submit"]');
  if (button.disabled) return;
  button.disabled = true; form.setAttribute("aria-busy", "true"); message("", status);
  try { await action(); } catch (error) { message(error.message, status); }
  finally { button.disabled = false; form.removeAttribute("aria-busy"); }
}
document.querySelectorAll("[data-reveal]").forEach(button => button.addEventListener("click", () => {
  const input = $(button.dataset.reveal), show = input.type === "password";
  input.type = show ? "text" : "password"; button.textContent = show ? "隐藏" : "显示";
  button.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  button.setAttribute("aria-pressed", String(show));
}));
document.querySelectorAll("[data-logout]").forEach(button => button.addEventListener("click", async () => {
  button.disabled = true;
  try { await api("/api/v1/auth/logout", "POST", {}); location.replace("/login"); }
  catch (error) { message(error.message); button.disabled = false; }
}));
$("login-form")?.addEventListener("submit", event => {
  event.preventDefault(); submit(event.target, async () => {
    session = await api("/api/v1/auth/login", "POST", {username: $("username").value, password: $("password").value});
    $("password").value = "";
    location.replace(session.user.must_change_password ? "/auth/password" : safeNext());
  });
});
$("password-form")?.addEventListener("submit", event => {
  event.preventDefault(); submit(event.target, async () => {
    if ($("new-password").value !== $("confirm-password").value) throw new Error("两次新密码不一致。");
    session = await api("/api/v1/auth/password", "POST", {current_password: $("current-password").value,
      new_password: $("new-password").value});
    event.target.reset(); location.replace("/auth");
  });
});
async function loadUsers() {
  const {users} = await api("/api/v1/auth/users");
  $("users").replaceChildren();
  for (const user of users) {
    const row = document.createElement("tr");
    for (const [label, text] of [["用户名", user.username], ["角色", roles[user.role]]]) {
      const cell = document.createElement("td"); cell.dataset.label = label; cell.textContent = text; row.append(cell);
    }
    const state = document.createElement("td"), badge = document.createElement("span");
    state.dataset.label = "状态"; badge.className = "badge" + (user.enabled ? "" : " off");
    badge.textContent = user.enabled ? "启用" : "禁用"; state.append(badge); row.append(state);
    const change = document.createElement("td"); change.dataset.label = "密码"; change.textContent = user.must_change_password ? "首次登录需修改" : "已设置"; row.append(change);
    const actions = document.createElement("td"); actions.dataset.label = "操作";
    for (const [kind, text] of [["toggle", user.enabled ? "禁用" : "启用"], ["reset", "重置密码"]]) {
      const button = document.createElement("button"); button.className = "button";
      button.textContent = text; button.addEventListener("click", () => openDialog(kind, user)); actions.append(button);
    }
    row.append(actions); $("users").append(row);
  }
}
function openDialog(action, user) {
  dialogAction = action; dialogUser = user; dialogKey = crypto.randomUUID(); $("user-form").reset(); message("", "dialog-status");
  const create = action === "create", password = action !== "toggle";
  $("create-fields").hidden = !create; $("password-fields").hidden = !password;
  $("new-username").required = create;
  $("temporary-password").required = password; $("temporary-confirm").required = password;
  const title = create ? "创建用户" : action === "reset" ? "重置密码" : user.enabled ? "禁用用户" : "启用用户";
  $("dialog-title").textContent = title; $("dialog-submit").textContent = title;
  $("dialog-hint").textContent = password ?
    (create ? "新用户首次登录必须修改临时密码。" : `为 ${user.username} 设置临时密码，所有现有会话将失效。`) :
    `确认${user.enabled ? "禁用" : "启用"} ${user.username}？${user.enabled ? "该账号将立即退出所有设备。" : "用户可使用原有密码重新登录。"}`;
  $("user-dialog").showModal();
}
$("create-user")?.addEventListener("click", () => openDialog("create"));
$("cancel-dialog")?.addEventListener("click", () => $("user-dialog").close());
$("user-dialog")?.addEventListener("close", () => { $("user-form").reset(); dialogUser = undefined; });
$("user-form")?.addEventListener("submit", event => {
  event.preventDefault(); submit(event.target, async () => {
    if (dialogAction !== "toggle" && $("temporary-password").value !== $("temporary-confirm").value)
      throw new Error("两次临时密码不一致。");
    if (dialogAction === "create") await api("/api/v1/auth/users", "POST", {
      username: $("new-username").value, password: $("temporary-password").value, role: $("new-role").value}, {"Idempotency-Key": dialogKey});
    else if (dialogAction === "reset") await api(`/api/v1/auth/users/${dialogUser.id}/reset-password`, "POST", {
      password: $("temporary-password").value}, {"Idempotency-Key": dialogKey, "If-Match": `"rev-${dialogUser.revision}"`});
    else await api(`/api/v1/auth/users/${dialogUser.id}`, "PATCH", {enabled: !dialogUser.enabled}, {"Idempotency-Key": dialogKey, "If-Match": `"rev-${dialogUser.revision}"`});
    $("user-dialog").close(); message("操作已保存。", "status", true); await loadUsers();
  }, "dialog-status");
});
async function init() {
  if (page === "login") return;
  session = await api("/api/v1/auth/me");
  const user = session.user;
  if (user.must_change_password && page !== "password") { location.replace("/auth/password"); return; }
  document.querySelectorAll("[data-admin]").forEach(el => { el.hidden = user.role !== "superadmin"; });
  if (page === "users") { $("current-user").textContent = user.username; await loadUsers(); }
  if (page === "password" && user.must_change_password)
    $("password-hint").textContent = "请先修改初始密码，再进入工作空间。";
  if (page === "account") {
    $("account-name").textContent = user.username; $("account-role").textContent = roles[user.role];
    $("account-permission").textContent = user.role === "superadmin" ?
      "你可以编辑项目、管理监控及账号，并管理工作空间用户。" : "你可以查看工作空间中的业务数据。";
  }
  setInterval(() => api("/api/v1/auth/me").then(value => { session = value; }).catch(error => message(error.message)), 30000);
}
init().catch(error => message(error.message));
// Revalidate on Back/Forward cache restore before displaying authenticated content.
addEventListener("pageshow", event => { if (event.persisted && page !== "login") location.reload(); });
