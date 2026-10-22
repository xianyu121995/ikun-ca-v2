#!/bin/zsh
# ikun.ca 东京账号管理（双击运行）。密码在 SSH 加密终端隐藏输入，不保存、不写日志。
PY=/Users/lvlei/.local/bin/python3.11
TOOL='/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/wss-receive-audit/release-integration/lightsail/auth_remote.py'
run(){ "$PY" "$TOOL" "$@"; }
while true; do
  echo "\n========== ikun 账号管理 =========="
  echo "1) 查看账号列表"
  echo "2) 添加朋友账号（只读用户）"
  echo "3) 重置某个账号的密码"
  echo "4) 禁用账号（立即踢下线，不能再登录）"
  echo "5) 重新启用账号"
  echo "6) 管理员(admin)忘记密码时恢复"
  echo "7) 添加超级管理员（和你同等权限）"
  echo "0) 退出"
  read "c?请输入数字: "
  case "$c" in
    1) run list ;;
    2) read "u?朋友的用户名(字母数字): "; [[ -n "$u" ]] && { echo "接下来输入两次【初始密码】(至少10位)，告诉朋友后他首次登录必须自己改。"; run create --username "$u"; } ;;
    3) read "u?要重置的用户名: "; [[ -n "$u" ]] && { echo "输入两次新的初始密码(至少10位)，对方登录后需自己改。"; run reset-password --username "$u"; } ;;
    4) read "u?要禁用的用户名: "; [[ -n "$u" ]] && run disable --username "$u" ;;
    5) read "u?要启用的用户名: "; [[ -n "$u" ]] && run enable --username "$u" ;;
    6) read "u?管理员用户名(一般是 admin): "; [[ -n "$u" ]] && { echo "输入两次新的初始密码，登录后需再改一次。"; run recover-admin --username "$u"; } ;;
    7) read "u?新管理员的用户名(字母数字): "; [[ -n "$u" ]] && { echo "接下来输入两次【初始密码】(至少10位)，对方首次登录必须自己改。"; run create-admin --username "$u"; } ;;
    0) exit 0 ;;
    *) echo "请输入 0-7" ;;
  esac
done
