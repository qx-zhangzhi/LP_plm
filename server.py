"""Modu MVP backend — a small self-hosted API and static-file server.

Run: python3 server.py
Open: http://127.0.0.1:8080
"""
from __future__ import annotations

import json
import sqlite3
import cgi
import re
import hashlib
import secrets
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, quote

ROOT = Path(__file__).parent
DB_PATH = ROOT / "modu.db"
UPLOADS = ROOT / "uploads"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

SEED_MODULES = [
    {"id": "M-001", "name": "皮带直线运动模组", "version": "1.3", "status": "已发布", "icon": "↔", "purpose": "用于轻载 XY 直线运动。适合标准自动化工位。", "tags": "负载 ≤ 8 kg · 速度 ≤ 1 m/s · 室内低粉尘", "scope": "负载 ≤ 8 kg；速度 ≤ 1 m/s；室内低粉尘", "avoid": "高冲击、高粉尘，或定位精度优于 ±0.05 mm", "interface": "2020 铝型材安装面 · NEMA17 · 标准孔距", "deps": "2020 铝型材、GT2 皮带、HGR15 导轨", "verify": "刚度、装配验证已完成；寿命测试待补", "uses": 6},
    {"id": "M-002", "name": "铝型材机架模块", "version": "2.1", "status": "已发布", "icon": "▦", "purpose": "用于轻型设备机架和防护结构，提供标准安装面、门板与线槽接口。", "tags": "2020 / 4040 型材 · 可快速拼装", "scope": "室内设备、轻载防护与工装；高度 ≤ 2.2 m", "avoid": "强腐蚀环境、承受持续冲击载荷", "interface": "2020 / 4040 型材槽口 · M5 紧固件", "deps": "2020 铝型材、角码、T 型螺母", "verify": "装配、公差与稳定性验证已完成", "uses": 11},
    {"id": "M-003", "name": "NEMA17 电机安装模块", "version": "1.0", "status": "已发布", "icon": "◉", "purpose": "用于 NEMA17 步进电机的快速安装与皮带、丝杠张紧调节。", "tags": "标准孔距 · 皮带 / 丝杠传动", "scope": "NEMA17 步进电机；扭矩 ≤ 0.6 N·m", "avoid": "高扭矩伺服电机与高振动场景", "interface": "31 mm 标准孔距 · M3 螺纹", "deps": "NEMA17 电机、M3 紧固件", "verify": "装配验证已完成", "uses": 4},
]
SEED_ISSUES = [
    {"id": "Q-027", "title": "皮带松弛", "module": "皮带直线运动模组", "source": "装配现场", "detail": "运行后预紧力不足", "status": "待处理"},
    {"id": "R-014", "title": "张紧器与侧板间隙不足", "module": "皮带直线运动模组", "source": "设计评审", "detail": "需调整侧板开孔并补充装配公差", "status": "待处理"},
]
SEED_MEMBERS = [("张工", "机械设计", "zhang", "designer"), ("李工", "制造工程", "li", "reviewer"), ("王工", "质量工程", "wang", "reviewer"), ("陈工", "项目负责人", "chen", "project_lead"), ("管理员", "系统管理员", "admin", "admin")]
SEED_PASSWORD = "modu-demo"
SESSIONS = {}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def initialize():
    with db() as conn:
        conn.executescript((ROOT / "schema.sql").read_text())
        columns = {row[1] for row in conn.execute("PRAGMA table_info(modules)")}
        migrations = {
            "gitlab_project": "ALTER TABLE modules ADD COLUMN gitlab_project TEXT NOT NULL DEFAULT ''",
            "gitlab_ref": "ALTER TABLE modules ADD COLUMN gitlab_ref TEXT NOT NULL DEFAULT ''",
            "release_tag": "ALTER TABLE modules ADD COLUMN release_tag TEXT NOT NULL DEFAULT ''",
            "frozen_at": "ALTER TABLE modules ADD COLUMN frozen_at TEXT",
            "deliverables_json": "ALTER TABLE modules ADD COLUMN deliverables_json TEXT NOT NULL DEFAULT '[]'",
        }
        for column, statement in migrations.items():
            if column not in columns:
                conn.execute(statement)
        conn.executescript((ROOT / "migrations" / "002_release_freeze.sql").read_text())
        conn.executescript((ROOT / "migrations" / "004_module_files.sql").read_text())
        issue_columns = {row[1] for row in conn.execute("PRAGMA table_info(issues)")}
        for column, statement in {
            "assigned_to": "ALTER TABLE issues ADD COLUMN assigned_to TEXT NOT NULL DEFAULT '未分配'",
            "created_by": "ALTER TABLE issues ADD COLUMN created_by TEXT NOT NULL DEFAULT '当前用户'",
        }.items():
            if column not in issue_columns:
                conn.execute(statement)
        if conn.execute("SELECT COUNT(*) FROM modules").fetchone()[0] == 0:
            conn.executemany("""INSERT INTO modules
                (id,name,version,status,icon,purpose,tags,scope,avoid,interface_spec,dependencies,verification,usage_count)
                VALUES (:id,:name,:version,:status,:icon,:purpose,:tags,:scope,:avoid,:interface,:deps,:verify,:uses)""", SEED_MODULES)
        if conn.execute("SELECT COUNT(*) FROM issues").fetchone()[0] == 0:
            module_ids = {row["name"]: row["id"] for row in conn.execute("SELECT id,name FROM modules")}
            conn.executemany("""INSERT INTO issues (id,title,module_id,module_name,source,detail,status)
                VALUES (:id,:title,:module_id,:module,:source,:detail,:status)""", [{**issue, "module_id": module_ids.get(issue["module"])} for issue in SEED_ISSUES])
        if conn.execute("SELECT COUNT(*) FROM members").fetchone()[0] == 0:
            conn.executemany("INSERT INTO members (display_name,role_name) VALUES (?,?)", [(name, role) for name, role, _, _ in SEED_MEMBERS])
        member_columns = {row[1] for row in conn.execute("PRAGMA table_info(members)")}
        for column, statement in {
            "login_name": "ALTER TABLE members ADD COLUMN login_name TEXT NOT NULL DEFAULT ''",
            "password_salt": "ALTER TABLE members ADD COLUMN password_salt TEXT NOT NULL DEFAULT ''",
            "password_hash": "ALTER TABLE members ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''",
            "role_code": "ALTER TABLE members ADD COLUMN role_code TEXT NOT NULL DEFAULT 'designer'",
        }.items():
            if column not in member_columns:
                conn.execute(statement)
        for display_name, _, login_name, role_code in SEED_MEMBERS:
            member = conn.execute("SELECT password_salt,password_hash FROM members WHERE display_name=?", (display_name,)).fetchone()
            if not member:
                conn.execute("INSERT INTO members (display_name,role_name) VALUES (?,?)", (display_name, next(role for name, role, _, _ in SEED_MEMBERS if name == display_name)))
                member = conn.execute("SELECT password_salt,password_hash FROM members WHERE display_name=?", (display_name,)).fetchone()
            if member and not member["password_hash"]:
                salt = secrets.token_hex(16)
                password_hash = hash_password(SEED_PASSWORD, salt)
                conn.execute("UPDATE members SET login_name=?,password_salt=?,password_hash=?,role_code=? WHERE display_name=?", (login_name, salt, password_hash, role_code, display_name))
    UPLOADS.mkdir(exist_ok=True)

def module_view(row):
    result = dict(row)
    result["interface"] = result.pop("interface_spec")
    result["deps"] = result.pop("dependencies")
    result["verify"] = result.pop("verification")
    result["uses"] = result.pop("usage_count")
    result["deliverables"] = json.loads(result.pop("deliverables_json") or "[]")
    return result

def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()

def next_id(conn, table, prefix):
    rows = conn.execute(f"SELECT id FROM {table} WHERE id GLOB ?", (prefix + "-*",)).fetchall()
    high = max((int(row[0].split("-")[1]) for row in rows if row[0].split("-")[1].isdigit()), default=0)
    return f"{prefix}-{high + 1:03d}"

class App(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def respond(self, status, data, headers=None):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("请求体必须是 JSON")

    def user(self):
        cookies = self.headers.get("Cookie", "")
        token = next((part.split("=", 1)[1] for part in cookies.split("; ") if part.startswith("modu_session=")), "")
        return SESSIONS.get(token)

    def require(self, *roles):
        user = self.user()
        if not user:
            self.respond(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"})
            return None
        if roles and user["role_code"] not in roles:
            self.respond(HTTPStatus.FORBIDDEN, {"error": "当前角色没有此操作权限"})
            return None
        return user

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.respond(HTTPStatus.OK, {"ok": True, "time": datetime.now(timezone.utc).isoformat()})
        if path == "/api/auth/me":
            user = self.user()
            return self.respond(HTTPStatus.OK, user) if user else self.respond(HTTPStatus.UNAUTHORIZED, {"error": "请先登录"})
        if path.startswith("/api/") and not self.require():
            return
        if path == "/api/modules":
            with db() as conn:
                modules = [module_view(row) for row in conn.execute("SELECT * FROM modules ORDER BY created_at DESC")]
            return self.respond(HTTPStatus.OK, modules)
        if path == "/api/issues":
            with db() as conn:
                issues = [dict(row) for row in conn.execute("""SELECT i.id,i.title,i.module_name AS module,i.source,i.detail,i.status,i.assigned_to,i.created_by,i.created_at,i.closed_at,
                    (SELECT COUNT(*) FROM issue_comments c WHERE c.issue_id=i.id) AS comment_count FROM issues i ORDER BY i.created_at DESC""")]
            return self.respond(HTTPStatus.OK, issues)
        if path == "/api/members":
            with db() as conn:
                members = [dict(row) for row in conn.execute("SELECT display_name,role_name,role_code FROM members WHERE active=1 ORDER BY id")]
            return self.respond(HTTPStatus.OK, members)
        if path == "/api/change-requests":
            with db() as conn:
                changes = [dict(row) for row in conn.execute("SELECT * FROM change_requests ORDER BY created_at DESC")]
            return self.respond(HTTPStatus.OK, changes)
        if path == "/api/notifications":
            with db() as conn:
                notifications = [dict(row) for row in conn.execute("SELECT * FROM notifications WHERE recipient_name=? ORDER BY is_read,created_at DESC", (self.user()["display_name"],))]
            return self.respond(HTTPStatus.OK, notifications)
        if path.startswith("/api/issues/") and path.endswith("/comments"):
            issue_id = path.split("/")[3]
            with db() as conn:
                comments = [dict(row) for row in conn.execute("SELECT id,author_name,body,created_at FROM issue_comments WHERE issue_id=? ORDER BY created_at", (issue_id,))]
            return self.respond(HTTPStatus.OK, comments)
        if path == "/api/reuse-requests":
            with db() as conn:
                requests = [dict(row) for row in conn.execute("SELECT * FROM reuse_requests ORDER BY created_at DESC")]
            return self.respond(HTTPStatus.OK, requests)
        if path.startswith("/api/modules/") and path.endswith("/files"):
            module_id = path.split("/")[3]
            with db() as conn:
                files = [dict(row) for row in conn.execute("SELECT id,filename,content_type,byte_size,uploaded_at FROM module_files WHERE module_id=? ORDER BY uploaded_at DESC", (module_id,))]
            for item in files:
                item["url"] = f"/api/files/{item['id']}/download"
            return self.respond(HTTPStatus.OK, files)
        if path.startswith("/api/files/") and path.endswith("/download"):
            file_id = path.split("/")[3]
            with db() as conn:
                row = conn.execute("SELECT filename,stored_name,content_type FROM module_files WHERE id=?", (file_id,)).fetchone()
            if not row or not (UPLOADS / row["stored_name"]).is_file():
                return self.respond(HTTPStatus.NOT_FOUND, {"error": "未找到文件"})
            payload = (UPLOADS / row["stored_name"]).read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", row["content_type"])
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(row['filename'])}")
            self.end_headers()
            return self.wfile.write(payload)
        if path.startswith("/api/modules/") and path.endswith("/release"):
            module_id = path.split("/")[3]
            with db() as conn:
                release = conn.execute("SELECT * FROM module_releases WHERE module_id = ? ORDER BY created_at DESC LIMIT 1", (module_id,)).fetchone()
            if not release:
                return self.respond(HTTPStatus.NOT_FOUND, {"error": "该模块尚未发布"})
            item = dict(release)
            item["manifest"] = json.loads(item.pop("manifest_json"))
            return self.respond(HTTPStatus.OK, item)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/auth/login":
                data = self.body()
                with db() as conn:
                    member = conn.execute("SELECT display_name,role_name,login_name,password_salt,password_hash,role_code FROM members WHERE login_name=? AND active=1", (data.get("login_name", ""),)).fetchone()
                if not member or not secrets.compare_digest(member["password_hash"], hash_password(str(data.get("password", "")), member["password_salt"])):
                    return self.respond(HTTPStatus.UNAUTHORIZED, {"error": "账号或密码错误"})
                token = secrets.token_urlsafe(32)
                user = {"display_name": member["display_name"], "role_name": member["role_name"], "role_code": member["role_code"]}
                SESSIONS[token] = user
                return self.respond(HTTPStatus.OK, user, {"Set-Cookie": f"modu_session={token}; HttpOnly; SameSite=Lax; Path=/"})
            if path == "/api/auth/logout":
                user = self.user()
                if user:
                    token = next((part.split("=", 1)[1] for part in self.headers.get("Cookie", "").split("; ") if part.startswith("modu_session=")), "")
                    SESSIONS.pop(token, None)
                return self.respond(HTTPStatus.OK, {"ok": True}, {"Set-Cookie": "modu_session=; Max-Age=0; Path=/"})
            if not self.require():
                return
            if path.startswith("/api/modules/") and path.endswith("/files"):
                return self.upload_file(path.split("/")[3])
            data = self.body()
            with db() as conn:
                if path.startswith("/api/modules/") and path.endswith("/publish"):
                    if not self.require("designer", "admin"):
                        return
                    module_id = path.split("/")[3]
                    module = conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
                    if not module:
                        return self.respond(HTTPStatus.NOT_FOUND, {"error": "未找到模块"})
                    if module["status"] != "草稿":
                        return self.respond(HTTPStatus.CONFLICT, {"error": "仅草稿模块可以发布；已发布版本不可覆盖"})
                    if not module["gitlab_project"].strip():
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "发布前必须关联 GitLab 项目"})
                    release_tag = f"modu/{module_id}/v{module['version']}"
                    required_artifacts = ["SolidWorks 源文件", "PDF", "STEP", "DXF", "BOM", "装配说明"]
                    deliverables = json.loads(module["deliverables_json"] or "[]")
                    missing = [artifact for artifact in required_artifacts if artifact not in deliverables]
                    if module["verification"] == "尚未开始验证":
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "发布前必须填写验证记录"})
                    if missing:
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "发布包缺少：" + "、".join(missing)})
                    manifest = {
                        "module": {"id": module_id, "name": module["name"], "version": module["version"]},
                        "required_artifacts": required_artifacts,
                        "deliverables": deliverables,
                        "verification": module["verification"],
                        "interface": module["interface_spec"],
                        "scope": module["scope"],
                    }
                    ref = module["gitlab_ref"].strip() or "main"
                    conn.execute("""INSERT INTO module_releases (module_id,module_version,release_tag,gitlab_project,gitlab_ref,manifest_json)
                        VALUES (?,?,?,?,?,?)""", (module_id, module["version"], release_tag, module["gitlab_project"], ref, json.dumps(manifest, ensure_ascii=False)))
                    conn.execute("""UPDATE modules SET status='已发布', release_tag=?, gitlab_ref=?, frozen_at=CURRENT_TIMESTAMP,
                        updated_at=CURRENT_TIMESTAMP WHERE id=?""", (release_tag, ref, module_id))
                    item = module_view(conn.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone())
                    return self.respond(HTTPStatus.CREATED, {"module": item, "release_tag": release_tag, "sync_status": "待同步", "manifest": manifest})
                if path == "/api/modules":
                    if not self.require("designer", "admin"):
                        return
                    required = ("name", "version", "purpose", "scope", "avoid", "interface")
                    if any(not str(data.get(key, "")).strip() for key in required):
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "请填写模块的用途、接口与应用边界"})
                    item = {"id": next_id(conn, "modules", "M"), "status": "草稿", "icon": "◫", "tags": data["scope"], "verify": "尚未开始验证", "uses": 0, **data}
                    item = {"gitlab_project": "", "gitlab_ref": "", "release_tag": "", "frozen_at": None, "deliverables_json": "[]", **item}
                    conn.execute("""INSERT INTO modules (id,name,version,status,icon,purpose,tags,scope,avoid,interface_spec,dependencies,verification,usage_count,gitlab_project,gitlab_ref,release_tag,frozen_at,deliverables_json)
                        VALUES (:id,:name,:version,:status,:icon,:purpose,:tags,:scope,:avoid,:interface,:deps,:verify,:uses,:gitlab_project,:gitlab_ref,:release_tag,:frozen_at,:deliverables_json)""", item)
                    return self.respond(HTTPStatus.CREATED, item)
                if path == "/api/issues":
                    if any(not str(data.get(key, "")).strip() for key in ("title", "module", "source")):
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "请填写问题标题、来源和关联模块"})
                    module_row = conn.execute("SELECT id FROM modules WHERE name = ?", (data["module"],)).fetchone()
                    item = {"id": next_id(conn, "issues", "Q"), "status": "待处理", "detail": "", "assigned_to": "未分配", "created_by": self.user()["display_name"], **data}
                    conn.execute("""INSERT INTO issues (id,title,module_id,module_name,source,detail,status,assigned_to,created_by)
                        VALUES (:id,:title,:module_id,:module,:source,:detail,:status,:assigned_to,:created_by)""", {**item, "module_id": module_row["id"] if module_row else None})
                    return self.respond(HTTPStatus.CREATED, item)
                if path.startswith("/api/issues/") and path.endswith("/comments"):
                    issue_id = path.split("/")[3]
                    if not str(data.get("body", "")).strip():
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "请填写讨论内容"})
                    if not conn.execute("SELECT 1 FROM issues WHERE id=?", (issue_id,)).fetchone():
                        return self.respond(HTTPStatus.NOT_FOUND, {"error": "未找到问题"})
                    author = self.user()["display_name"]
                    result = conn.execute("INSERT INTO issue_comments (issue_id,author_name,body) VALUES (?,?,?)", (issue_id, author, data["body"].strip()))
                    return self.respond(HTTPStatus.CREATED, {"id": result.lastrowid, "author_name": author, "body": data["body"].strip()})
                if path == "/api/reuse-requests":
                    if any(not str(data.get(key, "")).strip() for key in ("module_id", "module_version", "project_name", "operating_conditions")):
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "请填写复用申请信息"})
                    item = {"id": next_id(conn, "reuse_requests", "RR"), "status": "待确认", **data}
                    conn.execute("""INSERT INTO reuse_requests (id,module_id,module_version,project_name,operating_conditions,status)
                        VALUES (:id,:module_id,:module_version,:project_name,:operating_conditions,:status)""", item)
                    return self.respond(HTTPStatus.CREATED, item)
                if path == "/api/change-requests":
                    required = ("module_id", "title", "reason", "impact_summary", "approver_name")
                    if any(not str(data.get(key, "")).strip() for key in required):
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "请填写模块、变更原因、影响分析和审批人"})
                    module = conn.execute("SELECT name FROM modules WHERE id=?", (data["module_id"],)).fetchone()
                    if not module:
                        return self.respond(HTTPStatus.NOT_FOUND, {"error": "未找到关联模块"})
                    item = {"id": next_id(conn, "change_requests", "CR"), "module_name": module["name"], "initiator_name": self.user()["display_name"], "status": "待审批", "decision_note": "", **data}
                    conn.execute("""INSERT INTO change_requests (id,module_id,module_name,title,reason,impact_summary,initiator_name,approver_name,status,decision_note)
                        VALUES (:id,:module_id,:module_name,:title,:reason,:impact_summary,:initiator_name,:approver_name,:status,:decision_note)""", item)
                    conn.execute("""INSERT INTO notifications (recipient_name,kind,message,target_type,target_id)
                        VALUES (?,?,?,?,?)""", (item["approver_name"], "审批待办", f"{item['initiator_name']} 提交了变更 {item['id']}：{item['title']}", "change_request", item["id"]))
                    return self.respond(HTTPStatus.CREATED, item)
            self.respond(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
        except ValueError as exc:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except sqlite3.Error as exc:
            self.respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"数据库错误：{exc}"})

    def upload_file(self, module_id):
        if int(self.headers.get("Content-Length", "0")) > MAX_UPLOAD_BYTES:
            return self.respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "单个文件不能超过 100 MB"})
        if "multipart/form-data" not in self.headers.get("Content-Type", ""):
            return self.respond(HTTPStatus.BAD_REQUEST, {"error": "请使用 multipart/form-data 上传文件"})
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]})
        if "file" not in form or not getattr(form["file"], "file", None):
            return self.respond(HTTPStatus.BAD_REQUEST, {"error": "请选择要上传的文件"})
        upload = form["file"]
        filename = Path(upload.filename or "").name
        if not filename:
            return self.respond(HTTPStatus.BAD_REQUEST, {"error": "文件名无效"})
        raw = upload.file.read(MAX_UPLOAD_BYTES + 1)
        if len(raw) > MAX_UPLOAD_BYTES:
            return self.respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "单个文件不能超过 100 MB"})
        with db() as conn:
            if not conn.execute("SELECT 1 FROM modules WHERE id=?", (module_id,)).fetchone():
                return self.respond(HTTPStatus.NOT_FOUND, {"error": "未找到模块"})
            stored_name = f"{module_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{re.sub(r'[^A-Za-z0-9._-]', '_', filename)}"
            (UPLOADS / stored_name).write_bytes(raw)
            result = conn.execute("""INSERT INTO module_files (module_id,filename,stored_name,content_type,byte_size)
                VALUES (?,?,?,?,?)""", (module_id, filename, stored_name, upload.type or "application/octet-stream", len(raw)))
            item = {"id": result.lastrowid, "filename": filename, "content_type": upload.type or "application/octet-stream", "byte_size": len(raw), "url": f"/api/files/{result.lastrowid}/download"}
        return self.respond(HTTPStatus.CREATED, item)

    def do_PATCH(self):
        path = urlparse(self.path).path
        try:
            if not self.require():
                return
            data = self.body()
            if path.startswith("/api/modules/") and not path.endswith("/publish"):
                if not self.require("designer", "admin"):
                    return
                module_id = path.split("/")[3]
                with db() as conn:
                    current = conn.execute("SELECT * FROM modules WHERE id=?", (module_id,)).fetchone()
                    if not current:
                        return self.respond(HTTPStatus.NOT_FOUND, {"error": "未找到模块"})
                    if current["status"] != "草稿":
                        return self.respond(HTTPStatus.CONFLICT, {"error": "已发布模块不可直接编辑；请创建新的 Revision"})
                    allowed = {"purpose", "scope", "avoid", "interface", "deps", "verify", "gitlab_project", "gitlab_ref", "deliverables"}
                    changes = {key: value for key, value in data.items() if key in allowed}
                    if not changes:
                        return self.respond(HTTPStatus.BAD_REQUEST, {"error": "没有可保存的变更"})
                    mapping = {"interface": "interface_spec", "deps": "dependencies", "verify": "verification"}
                    assignments, values = [], []
                    for key, value in changes.items():
                        column = mapping.get(key, key)
                        if key == "deliverables":
                            column, value = "deliverables_json", json.dumps(value, ensure_ascii=False)
                        assignments.append(f"{column}=?")
                        values.append(value)
                    conn.execute(f"UPDATE modules SET {', '.join(assignments)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*values, module_id))
                    return self.respond(HTTPStatus.OK, module_view(conn.execute("SELECT * FROM modules WHERE id=?", (module_id,)).fetchone()))
            if path.startswith("/api/issues/") and path.endswith("/close"):
                issue_id = path.split("/")[3]
                with db() as conn:
                    result = conn.execute("UPDATE issues SET status='已关闭', closed_at=CURRENT_TIMESTAMP WHERE id=? AND status!='已关闭'", (issue_id,))
                    if result.rowcount == 0:
                        return self.respond(HTTPStatus.NOT_FOUND, {"error": "未找到待关闭的问题"})
                return self.respond(HTTPStatus.OK, {"id": issue_id, "status": "已关闭"})
            if path.startswith("/api/change-requests/") and path.endswith("/decision"):
                if not self.require("project_lead", "admin"):
                    return
                change_id = path.split("/")[3]
                status = data.get("status")
                if status not in ("已批准", "已驳回"):
                    return self.respond(HTTPStatus.BAD_REQUEST, {"error": "审批结果必须为已批准或已驳回"})
                with db() as conn:
                    current = conn.execute("SELECT * FROM change_requests WHERE id=?", (change_id,)).fetchone()
                    if not current or current["status"] != "待审批":
                        return self.respond(HTTPStatus.CONFLICT, {"error": "该变更不存在或已完成审批"})
                    note = str(data.get("decision_note") or "")
                    conn.execute("UPDATE change_requests SET status=?,decision_note=?,decided_at=CURRENT_TIMESTAMP WHERE id=?", (status, note, change_id))
                    conn.execute("""INSERT INTO notifications (recipient_name,kind,message,target_type,target_id)
                        VALUES (?,?,?,?,?)""", (current["initiator_name"], "审批结果", f"变更 {change_id} 已{status}：{note or '无补充说明'}", "change_request", change_id))
                return self.respond(HTTPStatus.OK, {"id": change_id, "status": status, "decision_note": note})
            self.respond(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
        except ValueError as exc:
            self.respond(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except sqlite3.Error as exc:
            self.respond(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"数据库错误：{exc}"})

def main():
    initialize()
    server = ThreadingHTTPServer(("127.0.0.1", 8080), App)
    print("Modu MVP is running at http://127.0.0.1:8080")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
