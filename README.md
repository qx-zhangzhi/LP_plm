# Modu 机械研发协作平台 MVP

这是一个可自托管的 MVP，无需安装第三方依赖。模块、问题与复用申请保存在项目目录的 SQLite 数据库中。

## 部署

在项目根目录运行 `python3 server.py`，再访问 `http://127.0.0.1:8080`。

首次启动会从 `schema.sql` 创建 `modu.db` 并写入演示数据。生产部署时应使用进程守护与反向代理，并将数据库目录纳入备份。

## 当前能力

- 模块库搜索、状态筛选与模块详情
- 创建模块草稿：用途、接口、适用范围、禁用条件和依赖
- 模块的应用边界、验证记录、发布包说明与变更影响提示
- 产品项目对已发布模块的版本引用
- 复用 / 改造申请的工作流演示
- 评审意见与现场问题登记、关闭与知识沉淀提示
- SQLite 持久化的模块、问题和复用申请
- 可由 GitLab Webhook、SolidWorks 插件或后续前端接入的 JSON API

## 说明

## API（当前）

- `GET/POST /api/modules`
- `POST /api/modules/{id}/publish` — 生成发布清单、冻结版本并等待 GitLab Release 同步
- `GET /api/modules/{id}/release`
- `GET/POST /api/issues`
- `PATCH /api/issues/{id}/close`
- `GET/POST /api/reuse-requests`
- `GET /api/health`

发布会要求模块先关联 GitLab 项目，并生成包含 CAD 源文件、PDF、STEP、DXF、BOM 与装配说明的发布清单。当前 MVP 已有后端 API，但尚未接入身份认证、GitLab / Git LFS、发布包和 SolidWorks 插件；这些是下一阶段的优先事项。
