#!/bin/zsh
# ikun.ca AI 设置（双击运行）。可选 Codex（用你的 ChatGPT Pro 登录）或 Gemini（密钥只在本窗口隐藏输入，只存本机）。
CFG="$HOME/Library/Application Support/ikun-ca-v2-c0-lite/config/ai.json"
PY=/Users/lvlei/.local/bin/python3.11
[[ -x "$PY" ]] || PY=/usr/bin/python3
show(){ "$PY" - "$CFG" <<'PYEOF'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception: print("当前状态：未设置"); raise SystemExit
k=d.get("api_key","")
print("当前状态：", "已启用" if d.get("enabled",True) else "已停用", "| 使用：", "Codex（ChatGPT Pro）" if d.get("provider")=="codex" else "Gemini", "| Gemini 密钥：", (k[:4]+"…"+k[-4:]) if k else "无", "| 代理：", d.get("proxy") or "不走代理")
PYEOF
}
save(){ IKUN_KEY="$1" IKUN_PROXY="$2" IKUN_ENABLED="$3" IKUN_PROVIDER="$4" "$PY" - "$CFG" <<'PYEOF'
import json,os,sys
p=sys.argv[1]
try: d=json.load(open(p))
except Exception: d={}
if os.environ["IKUN_KEY"]: d["api_key"]=os.environ["IKUN_KEY"]
d["proxy"]=os.environ["IKUN_PROXY"] or None
d["enabled"]=os.environ["IKUN_ENABLED"]=="1"
if os.environ.get("IKUN_PROVIDER"): d["provider"]=os.environ["IKUN_PROVIDER"]
d.setdefault("provider","gemini"); d.setdefault("model","gemini-flash-latest")
tmp=p+".tmp"; fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,"w") as f: json.dump(d,f)
os.replace(tmp,p); os.chmod(p,0o600); print("已保存。网站后台会自动读取，无需重启。")
PYEOF
}
testkey(){ "$PY" - "$CFG" <<'PYEOF'
import json,sys,subprocess
d=json.load(open(sys.argv[1])); args=["curl","-s","-o","/dev/null","-w","%{http_code}","--max-time","15","-H","x-goog-api-key: "+d["api_key"]]
if d.get("proxy"): args+=["-x",d["proxy"]]
code=subprocess.run(args+["https://generativelanguage.googleapis.com/v1beta/models"],capture_output=True,text=True).stdout
print({"200":"✅ 连接成功，密钥有效。","400":"❌ 密钥格式不对。","401":"❌ 密钥被拒绝（401）。新版 AQ. 密钥在部分账号上有这个问题，见说明。","403":"❌ 密钥被拒绝（可能填错或已删除）。","000":"❌ 连不上 Google：检查 Clash 是否开着、代理端口是否正确。"}.get(code,"❓ 返回 "+code))
PYEOF
}
while true; do
  echo "\n========== ikun AI 设置 (Gemini) =========="; show
  echo "1) 设置/更换 Gemini 密钥"
  echo "2) 设置代理端口（Clash，默认 7897）"
  echo "3) 测试连接"
  echo "4) 停用 AI"
  echo "5) 重新启用 AI"
  echo "6) 改用 Codex（ChatGPT Pro 登录，不需要密钥）"
  echo "7) 改用 Gemini"
  echo "0) 退出"
  read "c?请输入数字: "
  cur_proxy=$("$PY" -c "import json,sys;print((json.load(open(sys.argv[1])).get('proxy') or ''))" "$CFG" 2>/dev/null || echo "http://127.0.0.1:7897")
  [[ -z "$cur_proxy" && ! -f "$CFG" ]] && cur_proxy="http://127.0.0.1:7897"
  case "$c" in
    1) read -s "k?粘贴 Gemini 密钥（以 AQ. 或 AIza 开头，输入时不显示）: "; echo; k="${k//[[:space:]]/}"; [[ "$k" == AQ.* || "$k" == AIza* ]] && save "$k" "$cur_proxy" 1 || echo "看起来不是 Gemini 密钥，未保存。" ;;
    2) read "p?Clash 端口号（直接回车用 7897；输入 0 表示不走代理）: "; [[ -z "$p" ]] && p=7897; if [[ "$p" == 0 ]]; then save "" "" 1; else save "" "http://127.0.0.1:$p" 1; fi ;;
    3) [[ -f "$CFG" ]] && testkey || echo "还没有设置密钥。" ;;
    4) save "" "$cur_proxy" 0 ;;
    5) save "" "$cur_proxy" 1 ;;
    6) save "" "$cur_proxy" 1 codex ;;
    7) save "" "$cur_proxy" 1 gemini ;;
    0) exit 0 ;;
    *) echo "请输入 0-7" ;;
  esac
done
