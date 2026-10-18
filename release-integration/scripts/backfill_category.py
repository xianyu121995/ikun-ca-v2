#!/usr/bin/env python3
"""One-off (owner 2026-10-19): let AI classify existing projects into NFT / 发射台 / 新协议 / 撸毛.

Usage: backfill_category.py [--apply] [--all-memberships]
Dry run by default (prints the AI guess per project). Only touches projects whose category is
NULL/empty; never overwrites a type someone already chose. Each update bumps version/updated_at
so open editors see a fresh revision. Uses the same AI provider as Hunter (config/ai.json, Codex).
Back up projects.db first.
"""
import argparse, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / 'Library/Application Support/ikun-ca-v2-c0-lite'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/hunter-worker/python'))
from hunterradar import gemini  # noqa: E402

TYPES = ('NFT', '发射台', '新协议', '撸毛')
PROMPT = ("你是加密货币/Web3 项目研究助手。根据下面项目资料，判断项目类型，只能从 NFT、发射台、新协议、撸毛 四个里选一个最贴切的："
          "撸毛=主要玩法是做任务/交互/测试网拿空投积分；发射台=帮别人发币/发项目的平台；NFT=以 NFT 为核心；新协议=其他新的链上协议/产品/基础设施。"
          "实在判断不了给空字符串。只输出 JSON：{\"category\": ...}\n\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); ap.add_argument('--root', default=str(ROOT))
    ap.add_argument('--all-memberships', action='store_true', help='also hidden/removed projects (default: homepage-active only)')
    a = ap.parse_args()
    if not gemini.enabled():
        sys.exit('AI provider not configured (config/ai.json)')
    db = sqlite3.connect(str(Path(a.root) / 'data/projects/projects.db'), timeout=30)
    where = "deleted_at IS NULL AND (category IS NULL OR category='')" + ('' if a.all_memberships else " AND home_membership='active'")
    todo = db.execute(f"SELECT id,name,description,notes,website FROM projects WHERE {where} ORDER BY discovered_at DESC").fetchall()
    print(f'{len(todo)} projects to classify' + ('' if a.apply else ' (dry run)'), flush=True)
    done = 0
    for pid, name, description, notes, website in todo:
        try:
            value = gemini.generate_json(PROMPT + f"名称：{name}\n官网：{website}\n简介：{description}\n备注：{notes}")
        except gemini.AIUnavailable as exc:
            print('AI unavailable:', exc, '— stopping'); break
        guess = value.get('category') if isinstance(value, dict) else None
        guess = guess.strip() if isinstance(guess, str) else ''
        if guess not in TYPES:
            print(f'  ?    {name}  (AI 判断不了，保持未分类)', flush=True); continue
        print(f'  {guess:<4} {name}', flush=True)
        if a.apply:
            stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            with db:
                db.execute("UPDATE projects SET category=?, version=version+1, updated_at=? WHERE id=? AND (category IS NULL OR category='')", (guess, stamp, pid))
            done += 1
    print(f'{done} applied' if a.apply else 'dry run only; rerun with --apply')


if __name__ == '__main__':
    main()
