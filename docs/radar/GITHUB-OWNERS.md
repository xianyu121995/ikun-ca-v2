# 已核实的 GitHub owner

核对时间：2026-11-20。只采用官网或官方文档页面里写明的 `https://github.com/<owner>/<repo>` 链接。没有用名称搜索去猜账号。

## FLAP：`flap-sh`，已配置

官方文档 `docs.flap.sh` 直接链接到这个 owner 下的仓库：

- https://docs.flap.sh/en/flap/developers/vault-developers/quick-start-vault-developers 链接 `https://github.com/flap-sh/FlapVaultExample` 和 `https://github.com/flap-sh/flap-vault-component-template`
- https://docs.flap.sh/en/flap/v2/developers/bonding-curve/build-on-bonding-curve 同样链接上述仓库
- https://docs.flap.sh/en/flap/developers/vault-developers/case-study-beacon-upgradeable-vault 和 vault 规范页链接 `https://github.com/flap-sh/FlapVaultExample`

因此新公开仓库发现只扫描 `flap-sh`。默认每小时查一次名单。第一次只建基线。之后新增仓库才提醒，标题里有项目、仓库名，说明里有上述文档依据。不读取、不执行仓库内容。

## four.meme：官方 owner 未配置

官方 GitBook 开发页只给出原来的两个社区文档仓库：

- https://four-meme.gitbook.io/four.meme/developer/openfour-integration 写的是 `https://github.com/four-meme-community/openfour-docs`
- https://four-meme.gitbook.io/four.meme/developer/fourmeme-integration 写的是 `https://github.com/four-meme-community/fourmeme-docs`

没有看到官网或这份官方文档指向另一个 GitHub 组织。按要求不把 `four-meme-community` 当成官方 owner，所以不扫描它的新仓库。原来的文件树对比仍然只看着这两个已配置仓库。

如果以后官方文档明确写出别的 owner，把该 owner 和证据 URL 加进 `services/mode-radar/radar/config.json` 的 `probes.discover.owners`。文档里新出现、但不属于已核实 owner 的 GitHub 链接只会记成「未核实」，不会自动扩大扫描。

## 额度

未登录 GitHub API 大约每小时 60 次。文件树探针大约每 30 分钟 2 次，发现探针每小时大约 1 次（仓库超过 100 个才翻页）。这不是秒级监控。遇到限流、304 或中途失败时不更新基线，也不把失败报成仓库删除。
