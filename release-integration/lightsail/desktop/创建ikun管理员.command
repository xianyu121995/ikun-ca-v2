#!/bin/zsh
# 创建东京 ikun.ca 的初始超级管理员账号（只需在 SSH 终端隐藏输入两次密码）
PY=/Users/lvlei/.local/bin/python3.11
TOOL='/Users/lvlei/Documents/ChatGPT/ikun.ca开发/ikun-ca-v2-worktrees/wss-receive-audit/release-integration/lightsail/auth_remote.py'
echo "== 当前账号列表 =="
"$PY" "$TOOL" list || { echo "读取账号失败，请把上面的报错截图给 Claude。"; read -k1 "?按任意键关闭"; exit 1; }
echo
read "ok?列表为空才继续创建。继续创建用户名 admin 吗？(y/n) "
if [[ "$ok" == y* ]]; then
  "$PY" "$TOOL" bootstrap --username admin && echo "\n完成。打开 https://ikun.ca 用 admin 登录，首次登录会要求改密码。"
else
  echo "已取消，没有做任何修改。"
fi
read -k1 "?按任意键关闭"
