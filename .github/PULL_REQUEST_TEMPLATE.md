# 变更说明

本模板用于向 `main` 分支提交改动。

## 改动内容

<!-- 一句话说明这次改动做了什么 -->

## 关联 Issue

<!-- 如 Closes #12；无关联 Issue 可写「无」 -->

## 验证方式

- [ ] 服务端：`cd server && python -m pytest -q` 通过
- [ ] 管理台：`cd admin && pnpm typecheck && pnpm build` 通过
- [ ] Android：`cd android && ./gradlew assembleDebug` 通过（Windows：`gradlew.bat assembleDebug`）

## 其他影响

- [ ] 涉及数据库结构变更（已在 `app/db.py` 的 `init_db()` 中处理老库升级）
- [ ] 涉及配置项变更（已同步更新 `.env.example` 与 README 的配置表）

## 提交信息

- [ ] 标题一行说明改了什么，不超过 50 字，不加句号
- [ ] 正文解释了为什么改以及机制与后果
