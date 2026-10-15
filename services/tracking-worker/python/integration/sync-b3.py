"""Apply minimal reviewed presentation changes only inside the ignored frozen preview."""

import difflib
import importlib.util
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("assembly", HERE / "prepare-b3.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
P = a.PREVIEW


def original(path):
    return subprocess.check_output(["git", "show", a.PINS["tracking_ui"] + ":" + path], cwd=a.ROOT, text=True)


def main():
    for relative in ("services/tracking-worker/python/tracking", "schemas/tracking"):
        if (P / relative).exists():
            shutil.rmtree(P / relative)
        shutil.copytree(
            a.ROOT / relative, P / relative, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__")
        )
    shutil.copyfile(
        a.ROOT / "services/tracking-worker/src/main.ts", P / "services/tracking-worker/src/main.ts"
    )
    shutil.copytree(HERE / "website", P / "apps/website", dirs_exist_ok=True)
    source = "apps/website/features/tracking/final/tracking-page.tsx"
    old = original(source)
    s = old

    def edit(before, after):
        nonlocal s
        if before not in s:
            raise RuntimeError("PATCH_CONTEXT: " + before[:80])
        s = s.replace(before, after)

    edit("useEffect, useRef, useState", "useEffect, useRef, useState, type ReactNode")
    edit(
        "onRemove?: (key: string) => Promise<void>;",
        "onRemove?: (key: string) => Promise<void>;\n  live?: {accountMenu:ReactNode;canManage:boolean;refresh:()=>void;onOpenPost:(post:Post)=>void;manageActions:(account:Account)=>ReactNode;addForm:(close:()=>void)=>ReactNode;pagination:ReactNode};",
    )
    edit(
        "function MediaPreview({ media }: { media: Media | null })",
        "function MediaPreview({ media, unknown }: { media: Media | null; unknown?:boolean })",
    )
    edit(
        'media ? "媒体暂不可用" : "无配图"', 'unknown ? "媒体信息未提供" : media ? "媒体暂不可用" : "无配图"'
    )
    edit(
        "loading = false, onAdd, onRemove }: TrackingPageProps",
        "loading = false, onAdd, onRemove, live }: TrackingPageProps",
    )
    edit("<span className={s.admin}", "{live?.accountMenu ?? <span className={s.admin}")
    edit('"A" : "?"}</span></div></div>', '"A" : "?"}</span>}</div></div>')
    edit('failed: "失败", unknown:', 'failed: "失败", stopped:"已停止", unknown:')
    edit(
        'mode === "demo" && !!onAdd && !!onRemove',
        '(mode === "demo" || live?.canManage === true) && !!onAdd && !!onRemove',
    )
    edit(
        "selectPosts(accounts, posts, filters, now ?? 0)",
        'selectPosts(accounts, posts, filters, now ?? 0, mode === "live" ? "received" : "occurred")',
    )
    edit('["S", "A", "B"].indexOf(a.grade)', '["S", "A", "B"].indexOf(a.grade ?? "")')
    edit('["S", "A", "B"].indexOf(b.grade)', '["S", "A", "B"].indexOf(b.grade ?? "")')
    edit(
        "notify(`「${deleting.name}」已从演示监控列表删除，未触碰真实监控`)",
        'notify(mode === "live" ? "移除请求已持久受理，等待远端核验；历史与主页保持独立" : `「${deleting.name}」已从演示监控列表删除，未触碰真实监控`)',
    )
    edit(
        'notify("本地演示删除失败，账号列表未确认变更。", "danger")',
        'notify(mode === "live" ? "移除结果待核对，请查看命令与错误状态" : "本地演示删除失败，账号列表未确认变更。", "danger")',
    )
    edit(
        'manageable ? <Button size="sm" variant="danger"',
        'manageable ? <span>{live?.manageActions(account)}<Button size="sm" variant="danger"',
    )
    edit("}}>删除</Button> : <span>只读</span>", "}}>删除</Button></span> : <span>只读</span>")
    edit('"页面演示中" : "未接入服务"', '"页面演示中" : "本地 API 候选"')
    edit('"只读 · 未接真实数据"', '"本地服务 · 远端按核验状态显示"')
    edit('disabled={loading || mode !== "demo"}', 'disabled={loading || mode !== "demo" && !live}')
    edit(
        'reset(); notify("已刷新演示列表 · 不会请求真实推文 API");',
        'reset(); if(live)live.refresh();else notify("已刷新演示列表 · 不会请求真实推文 API");',
    )
    edit(
        '{loading ? "—" : stats.today}',
        '{loading || mode === "live" && posts.some(post=>post.published_at===null) ? "—" : stats.today}',
    )
    edit("<span>今日新推文</span>", '<span>{mode === "live" ? "本页今日动态" : "今日新推文"}</span>')
    edit(
        'type="checkbox" checked={filters.important}',
        'type="checkbox" disabled={mode === "live"} title={mode === "live" ? "重要标记未提供，当前不可用" : undefined} checked={filters.important}',
    )
    edit(
        "· 按最新时间排序",
        '· {mode === "live" ? "按接收时间排序 · 发布时间排序待协议裁定" : "按最新时间排序"}',
    )
    edit(
        "<MediaPreview media={post.media} />",
        '<MediaPreview media={post.media} unknown={mode === "live" && !post.media_available} />',
    )
    edit(
        'onClick={() => notify(mode === "demo" ?',
        'onClick={() => live ? live.onOpenPost(post) : notify(mode === "demo" ?',
    )
    edit("<div className={s.feedFooter}>", "{live ? live.pagination : <div className={s.feedFooter}>")
    edit("</nav></div></section>", "</nav></div>}</section>")
    edit(
        "<span>UI 可点击演示　·　未接真实 NEW_TWEET API　·　未修改 tracking.db</span>",
        '<span>{mode === "live" ? "本地 Tracking API · 数据来自本库 · 不代表真实平台已验收" : "UI 可点击演示　·　未接真实 NEW_TWEET API　·　未修改 tracking.db"}</span>',
    )
    edit('"只读展示 · 真实身份与监控数据未接入"', '"仅筛选本页已加载记录 · 非 S/A/B 记录保留在管理"')
    edit("{adding && <form", "{adding && (live ? live.addForm(()=>setAdding(false)) : <form")
    edit("确认添加（模拟）</Button></div></form>}", "确认添加（模拟）</Button></div></form>)}")
    edit("minWidth={650}", "minWidth={800}")
    edit(
        "本窗口只模拟管理界面：增加账号不会自动获取历史推文；删除会从演示账号列表和当前推文信息流隐藏对应记录，不操作真实监控或数据库。",
        '{mode === "live" ? "启停与移除等待远端核验；未知状态不能视为成功。不会修改主页项目。" : "本窗口只模拟管理界面；不会修改真实监控。"}',
    )
    edit(
        "description={deleting ? `确定从演示监控列表删除",
        'description={mode === "live" ? "请求移除此订阅；远端核验前保留，推文历史和主页项目不受影响。" : deleting ? `确定从演示监控列表删除',
    )
    edit(">确认删除（演示）</Button>", '>{mode === "live" ? "确认请求移除" : "确认删除（演示）"}</Button>')
    edit(
        "<span>仅确认当前演示账号。</span>",
        '<span>{mode === "live" ? "此操作只影响当前订阅。" : "仅确认当前演示账号。"}</span>',
    )
    (P / source).write_text(s)
    model = "apps/website/features/tracking/final/model.ts"
    m0 = original(model)
    m = m0
    m = m.replace("note: string; grade: Grade;", 'note: string; grade: Grade | "C" | "D" | null;')
    m = m.replace('"failed" | "unknown";', '"failed" | "unknown" | "stopped";')
    m = m.replace(
        "body: string; important: boolean;",
        "body: string; important: boolean | null; original_url?:string; media_available?:boolean; received_at?:string;",
    )
    m = m.replace(
        "filters: Filters, now: number)",
        'filters: Filters, now: number, order: "occurred" | "received" = "occurred")',
    )
    m = m.replace(".includes(account.grade)", '.includes(account.grade ?? "")')
    m = m.replace("}).sort((a, b) =>", '}).sort((a, b) => order === "received" ? 0 :')
    (P / model).write_text(m)
    patch = "".join(
        difflib.unified_diff(
            old.splitlines(True), s.splitlines(True), fromfile="a/" + source, tofile="b/" + source
        )
    )
    patch += "".join(
        difflib.unified_diff(
            m0.splitlines(True), m.splitlines(True), fromfile="a/" + model, tofile="b/" + model
        )
    )
    (HERE / "patches/tracking-live.patch").write_text(patch)
    print("Tracking candidate overlaid; frozen source remains unchanged")


if __name__ == "__main__":
    main()
