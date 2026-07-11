# =========================
# main.py (1/20)
# =========================

import os
import io
import re
import json
import time
import shutil
import signal
import zipfile
import asyncio
import traceback
import subprocess
import threading
from pathlib import Path
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    send_from_directory,
    send_file,
    abort,
)

# =========================
# Flask
# =========================

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this")

# =========================
# 基本フォルダ
# =========================

BASE_DIR = Path(__file__).parent.resolve()

BOTS_DIR = BASE_DIR / "bots"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

USERS_FILE = BASE_DIR / "users.json"
TOKENS_FILE = BASE_DIR / "tokens.json"

BOTS_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# =========================
# 実行中Bot管理
# =========================

running_processes = {}
process_logs = {}

# =========================
# NGワード
# =========================

BANNED_KEYWORDS = [
    "os.remove(",
    "shutil.rmtree(",
    "subprocess.Popen(",
    "eval(",
    "exec(",
]

# =========================
# JSON Utility
# =========================

def load_json(path, default=None):
    if default is None:
        default = {}

    if not Path(path).exists():
        return default

    # =========================
# ユーザーフォルダ関連
# =========================

def ensure_user_folder(user_key: str) -> Path:
    """
    bots/<user_key> を作成して返す
    """
    user_dir = BOTS_DIR / user_key
    user_dir.mkdir(parents=True, exist_ok=True)

    (user_dir / "logs").mkdir(exist_ok=True)
    (user_dir / "data").mkdir(exist_ok=True)
    (user_dir / "cogs").mkdir(exist_ok=True)

    return user_dir


def get_bot_file(user_key: str) -> Path:
    return ensure_user_folder(user_key) / "main.py"


def get_requirements_file(user_key: str) -> Path:
    return ensure_user_folder(user_key) / "requirements.txt"


def get_log_file(user_key: str) -> Path:
    return ensure_user_folder(user_key) / "logs" / "latest.log"


# =========================
# 認証
# =========================

def validate_token(token: str):
    if not token:
        return None

    return valid_tokens.get(token)


# =========================
# コードチェック
# =========================

def check_code(code: str):
    """
    危険なコードを簡易チェック
    """

    lowered = code.lower()

    for keyword in BANNED_KEYWORDS:
        if keyword.lower() in lowered:
            return False, f"禁止されたコードが含まれています: {keyword}"

    return True, None


# =========================
# ログ
# =========================

def append_log(user_key: str, text: str):
    logfile = get_log_file(user_key)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(logfile, "a", encoding="utf-8") as f:
        f.write(f"[{now}] {text}\n")


def read_log(user_key: str):
    logfile = get_log_file(user_key)

    if not logfile.exists():
        return ""

    with open(logfile, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


users = load_json(USERS_FILE, {})
valid_tokens = load_json(TOKENS_FILE, {})
# =========================
# Bot実行管理
# =========================

def is_running(user_key: str) -> bool:
    process = running_processes.get(user_key)

    if process is None:
        return False

    return process.poll() is None


def stop_process(user_key: str):
    process = running_processes.get(user_key)

    if process is None:
        return False

    if process.poll() is None:
        try:
            process.terminate()

            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()

            append_log(user_key, "Botを停止しました。")

        except Exception as e:
            append_log(user_key, f"停止エラー: {e}")

    running_processes.pop(user_key, None)
    process_logs.pop(user_key, None)

    return True


def start_process(user_key: str):
    if is_running(user_key):
        return False, "既に起動しています。"

    user_dir = ensure_user_folder(user_key)

    bot_file = get_bot_file(user_key)

    if not bot_file.exists():
        return False, "main.py が存在しません。"

    logfile = open(
        get_log_file(user_key),
        "a",
        encoding="utf-8"
    )

    process = subprocess.Popen(
        ["python", "main.py"],
        cwd=user_dir,
        stdout=logfile,
        stderr=subprocess.STDOUT,
        text=True
    )

    running_processes[user_key] = process
    process_logs[user_key] = logfile

    append_log(user_key, "Botを起動しました。")

    return True, "起動しました。"


def restart_process(user_key: str):
    stop_process(user_key)
    return start_process(user_key)

# =========================
# ディレクトリ操作
# =========================

HIDDEN_NAMES = {
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
}


def build_tree(path: Path):
    """
    ファイルツリーを辞書形式で返す
    """

    items = []

    try:
        children = sorted(
            path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower())
        )
    except Exception:
        return items

    for child in children:

        if child.name in HIDDEN_NAMES:
            continue

        node = {
            "name": child.name,
            "path": str(child.relative_to(path.parent)).replace("\\", "/"),
            "is_dir": child.is_dir(),
        }

        if child.is_dir():
            node["children"] = build_tree(child)

        items.append(node)

    return items


def safe_path(user_key: str, relative_path: str) -> Path:
    """
    bots/<user>/ 以下のみアクセス可能
    """

    root = ensure_user_folder(user_key).resolve()

    target = (root / relative_path).resolve()

    if not str(target).startswith(str(root)):
        raise PermissionError("Invalid path")

    return target


# =========================
# ファイル操作
# =========================

def read_file(user_key: str, relative_path: str):
    path = safe_path(user_key, relative_path)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def write_file(user_key: str, relative_path: str, content: str):
    path = safe_path(user_key, relative_path)

    ok, reason = check_code(content)

    if not ok and path.name.endswith(".py"):
        return False, reason

    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    append_log(user_key, f"保存: {relative_path}")

    return True, "保存しました。"

# =========================
# ファイル・フォルダ作成／削除
# =========================

def create_file(user_key: str, relative_path: str):
    path = safe_path(user_key, relative_path)

    if path.exists():
        return False, "既に存在します。"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()

    append_log(user_key, f"ファイル作成: {relative_path}")
    return True, "ファイルを作成しました。"


def create_folder(user_key: str, relative_path: str):
    path = safe_path(user_key, relative_path)

    if path.exists():
        return False, "既に存在します。"

    path.mkdir(parents=True)

    append_log(user_key, f"フォルダ作成: {relative_path}")
    return True, "フォルダを作成しました。"


def delete_path(user_key: str, relative_path: str):
    path = safe_path(user_key, relative_path)

    if not path.exists():
        return False, "存在しません。"

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()

    append_log(user_key, f"削除: {relative_path}")
    return True, "削除しました。"


def rename_path(user_key: str, old_path: str, new_name: str):
    src = safe_path(user_key, old_path)

    if not src.exists():
        return False, "存在しません。"

    dst = src.parent / new_name

    if dst.exists():
        return False, "同じ名前が既に存在します。"

    src.rename(dst)

    append_log(user_key, f"名前変更: {old_path} -> {new_name}")
    return True, "名前を変更しました。"


# =========================
# ZIPダウンロード
# =========================

def create_zip(user_key: str):
    user_dir = ensure_user_folder(user_key)

    memory_file = io.BytesIO()

    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(user_dir):
            dirs[:] = [d for d in dirs if d not in HIDDEN_NAMES]

            for file in files:
                full = Path(root) / file
                arc = full.relative_to(user_dir)
                zf.write(full, arc)

    memory_file.seek(0)

    return memory_file

# =========================
# トップページ
# =========================

@app.route("/")
def index():
    return render_template("index.html")


# =========================
# ダッシュボード
# =========================

@app.route("/dashboard")
def dashboard():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)

    if not user_key:
        return render_template(
            "error.html",
            message="無効なトークンです。"
        ), 403

    user_dir = ensure_user_folder(user_key)

    tree = build_tree(user_dir)

    return render_template(
        "dashboard.html",
        token=token,
        user_key=user_key,
        tree=tree,
        running=is_running(user_key)
    )


# =========================
# API：ファイルツリー
# =========================

@app.route("/api/tree")
def api_tree():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)

    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    tree = build_tree(ensure_user_folder(user_key))

    return jsonify({
        "success": True,
        "tree": tree
    })


# =========================
# API：ファイル読み込み
# =========================

@app.route("/api/file")
def api_file():
    token = request.args.get("token", "").strip()
    path = request.args.get("path", "")

    user_key = validate_token(token)

    if not user_key:
        return jsonify({
            "success": False
        }), 403

    try:
        content = read_file(user_key, path)

        return jsonify({
            "success": True,
            "content": content
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 400

# =========================
# API：ファイル保存
# =========================

@app.route("/api/file", methods=["POST"])
def api_save_file():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    relative_path = str(data.get("path", "")).strip()
    content = data.get("content", "")

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        success, message = write_file(
            user_key,
            relative_path,
            content
        )

        return jsonify({
            "success": success,
            "message": message
        })

    except PermissionError:
        return jsonify({
            "success": False,
            "message": "Permission denied"
        }), 403

    except Exception as e:
        append_log(user_key, f"保存エラー: {e}")

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：新規ファイル作成
# =========================

@app.route("/api/create_file", methods=["POST"])
def api_create_file():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    relative_path = str(data.get("path", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({"success": False}), 403

    try:
        success, message = create_file(
            user_key,
            relative_path
        )

        return jsonify({
            "success": success,
            "message": message
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })

# =========================
# API：フォルダ作成
# =========================

@app.route("/api/create_folder", methods=["POST"])
def api_create_folder():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    relative_path = str(data.get("path", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        success, message = create_folder(
            user_key,
            relative_path
        )

        return jsonify({
            "success": success,
            "message": message
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：削除
# =========================

@app.route("/api/delete", methods=["POST"])
def api_delete():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    relative_path = str(data.get("path", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        success, message = delete_path(
            user_key,
            relative_path
        )

        return jsonify({
            "success": success,
            "message": message
        })

    except PermissionError:
        return jsonify({
            "success": False,
            "message": "Permission denied"
        }), 403

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：名前変更
# =========================

@app.route("/api/rename", methods=["POST"])
def api_rename():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    old_path = str(data.get("old_path", "")).strip()
    new_name = str(data.get("new_name", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        success, message = rename_path(
            user_key,
            old_path,
            new_name
        )

        return jsonify({
            "success": success,
            "message": message
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================
# API：Bot起動
# =========================

@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        success, message = start_process(user_key)

        return jsonify({
            "success": success,
            "message": message,
            "running": is_running(user_key)
        })

    except Exception as e:
        append_log(user_key, traceback.format_exc())

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：Bot停止
# =========================

@app.route("/api/stop", methods=["POST"])
def api_stop():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        stop_process(user_key)

        return jsonify({
            "success": True,
            "message": "停止しました。",
            "running": False
        })

    except Exception as e:
        append_log(user_key, traceback.format_exc())

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：Bot再起動
# =========================

@app.route("/api/restart", methods=["POST"])
def api_restart():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        success, message = restart_process(user_key)

        return jsonify({
            "success": success,
            "message": message,
            "running": is_running(user_key)
        })

    except Exception as e:
        append_log(user_key, traceback.format_exc())

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================
# API：ログ取得
# =========================

@app.route("/api/log")
def api_log():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        log_text = read_log(user_key)

        return jsonify({
            "success": True,
            "log": log_text,
            "running": is_running(user_key)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：ZIPダウンロード
# =========================

@app.route("/download")
def download_zip():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        abort(403)

    try:
        zip_file = create_zip(user_key)

        return send_file(
            zip_file,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{user_key}.zip"
        )

    except Exception as e:
        append_log(user_key, f"ZIP作成エラー: {e}")
        abort(500)


# =========================
# API：ステータス取得
# =========================

@app.route("/api/status")
def api_status():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    process = running_processes.get(user_key)

    pid = process.pid if process and process.poll() is None else None

    return jsonify({
        "success": True,
        "running": is_running(user_key),
        "pid": pid
    })
# =========================
# API：ファイルアップロード
# =========================

@app.route("/api/upload", methods=["POST"])
def api_upload():
    token = request.form.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    if "file" not in request.files:
        return jsonify({
            "success": False,
            "message": "ファイルがありません。"
        }), 400

    upload = request.files["file"]

    relative_path = request.form.get("path", "").strip()

    try:
        save_path = safe_path(
            user_key,
            relative_path
        )

        if save_path.is_dir():
            save_path = save_path / upload.filename

        save_path.parent.mkdir(parents=True, exist_ok=True)

        upload.save(save_path)

        append_log(
            user_key,
            f"アップロード: {save_path.name}"
        )

        return jsonify({
            "success": True,
            "message": "アップロードしました。"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：requirements.txt インストール
# =========================

@app.route("/api/install", methods=["POST"])
def api_install():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    requirements = get_requirements_file(user_key)

    if not requirements.exists():
        return jsonify({
            "success": False,
            "message": "requirements.txt がありません。"
        })

    try:
        result = subprocess.run(
            [
                "pip",
                "install",
                "-r",
                str(requirements)
            ],
            capture_output=True,
            text=True
        )

        append_log(user_key, result.stdout)

        if result.stderr:
            append_log(user_key, result.stderr)

        return jsonify({
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr
        })

    except Exception as e:
        append_log(user_key, traceback.format_exc())

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================
# API：コンソール入力
# =========================

@app.route("/api/console", methods=["POST"])
def api_console():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    command = str(data.get("command", ""))

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    process = running_processes.get(user_key)

    if process is None or process.poll() is not None:
        return jsonify({
            "success": False,
            "message": "Botは起動していません。"
        })

    if process.stdin is None:
        return jsonify({
            "success": False,
            "message": "標準入力が利用できません。"
        })

    try:
        process.stdin.write(command + "\n")
        process.stdin.flush()

        append_log(user_key, f">>> {command}")

        return jsonify({
            "success": True,
            "message": "送信しました。"
        })

    except Exception as e:
        append_log(user_key, traceback.format_exc())

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：新規Bot作成
# =========================

@app.route("/api/create_bot", methods=["POST"])
def api_create_bot():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    try:
        user_dir = ensure_user_folder(user_key)

        main_file = user_dir / "main.py"
        req_file = user_dir / "requirements.txt"

        if not main_file.exists():
            main_file.write_text(
                '''import discord
from discord.ext import commands

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

@bot.event
async def on_ready():
    print(f"{bot.user} Ready")

bot.run("TOKEN")
''',
                encoding="utf-8"
            )

        if not req_file.exists():
            req_file.write_text(
                "discord.py\n",
                encoding="utf-8"
            )

        return jsonify({
            "success": True,
            "message": "Botを作成しました。"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================
# API：requirements.txt 自動生成
# =========================

@app.route("/api/generate_requirements", methods=["POST"])
def api_generate_requirements():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        main_file = get_bot_file(user_key)

        if not main_file.exists():
            return jsonify({
                "success": False,
                "message": "main.py が存在しません。"
            })

        code = main_file.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        imports = set()

        for line in code.splitlines():
            line = line.strip()

            if line.startswith("import "):
                modules = line.replace("import ", "").split(",")

                for module in modules:
                    imports.add(module.strip().split(".")[0])

            elif line.startswith("from "):
                module = line.split()[1].split(".")[0]
                imports.add(module)

        ignore = {
            "os",
            "sys",
            "io",
            "json",
            "time",
            "math",
            "random",
            "asyncio",
            "pathlib",
            "typing",
            "datetime",
            "traceback",
            "subprocess",
            "threading",
            "collections",
            "itertools",
            "functools",
            "re",
            "string",
            "zipfile",
            "shutil"
        }

        packages = sorted(imports - ignore)

        requirements = "\n".join(packages)

        get_requirements_file(user_key).write_text(
            requirements,
            encoding="utf-8"
        )

        append_log(
            user_key,
            "requirements.txt を自動生成しました。"
        )

        return jsonify({
            "success": True,
            "packages": packages
        })

    except Exception as e:
        append_log(user_key, traceback.format_exc())

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：ファイル一覧
# =========================

@app.route("/api/files")
def api_files():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    return jsonify({
        "success": True,
        "tree": build_tree(
            ensure_user_folder(user_key)
        )
    })

# =========================
# API：ファイル検索
# =========================

@app.route("/api/search")
def api_search():
    token = request.args.get("token", "").strip()
    keyword = request.args.get("q", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    if not keyword:
        return jsonify({
            "success": True,
            "results": []
        })

    results = []

    user_dir = ensure_user_folder(user_key)

    try:
        for root, dirs, files in os.walk(user_dir):

            dirs[:] = [
                d for d in dirs
                if d not in HIDDEN_NAMES
            ]

            for file in files:

                full_path = Path(root) / file

                relative = full_path.relative_to(user_dir)

                if keyword.lower() in file.lower():
                    results.append({
                        "type": "file",
                        "path": str(relative).replace("\\", "/")
                    })
                    continue

                try:
                    content = full_path.read_text(
                        encoding="utf-8",
                        errors="ignore"
                    )

                    if keyword.lower() in content.lower():
                        results.append({
                            "type": "content",
                            "path": str(relative).replace("\\", "/")
                        })

                except Exception:
                    pass

        return jsonify({
            "success": True,
            "results": results
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：ログクリア
# =========================

@app.route("/api/clear_log", methods=["POST"])
def api_clear_log():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    try:
        logfile = get_log_file(user_key)

        logfile.write_text(
            "",
            encoding="utf-8"
        )

        append_log(
            user_key,
            "ログをクリアしました。"
        )

        return jsonify({
            "success": True
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================
# API：ファイルダウンロード
# =========================

@app.route("/api/download")
def api_download_file():
    token = request.args.get("token", "").strip()
    relative_path = request.args.get("path", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        file_path = safe_path(user_key, relative_path)

        if not file_path.exists():
            return jsonify({
                "success": False,
                "message": "ファイルが存在しません。"
            }), 404

        if file_path.is_dir():
            return jsonify({
                "success": False,
                "message": "フォルダはダウンロードできません。"
            }), 400

        return send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name
        )

    except PermissionError:
        return jsonify({
            "success": False,
            "message": "Permission denied"
        }), 403

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：ファイル複製
# =========================

@app.route("/api/copy", methods=["POST"])
def api_copy():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    source = str(data.get("source", "")).strip()
    destination = str(data.get("destination", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        src = safe_path(user_key, source)
        dst = safe_path(user_key, destination)

        if not src.exists():
            return jsonify({
                "success": False,
                "message": "コピー元が存在しません。"
            })

        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        append_log(
            user_key,
            f"コピー: {source} -> {destination}"
        )

        return jsonify({
            "success": True,
            "message": "コピーしました。"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================
# API：ファイル移動
# =========================

@app.route("/api/move", methods=["POST"])
def api_move():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    source = str(data.get("source", "")).strip()
    destination = str(data.get("destination", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        src = safe_path(user_key, source)
        dst = safe_path(user_key, destination)

        if not src.exists():
            return jsonify({
                "success": False,
                "message": "移動元が存在しません。"
            })

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))

        append_log(
            user_key,
            f"移動: {source} -> {destination}"
        )

        return jsonify({
            "success": True,
            "message": "移動しました。"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：実行中一覧
# =========================

@app.route("/api/processes")
def api_processes():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    processes = []

    for key, process in running_processes.items():
        if process.poll() is None:
            processes.append({
                "user": key,
                "pid": process.pid
            })

    return jsonify({
        "success": True,
        "processes": processes
    })


# =========================
# API：ヘルスチェック
# =========================

@app.route("/api/ping")
def api_ping():
    return jsonify({
        "success": True,
        "status": "online",
        "time": datetime.now().isoformat()
    })

# =========================
# API：プロジェクト情報
# =========================

@app.route("/api/project")
def api_project():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    try:
        user_dir = ensure_user_folder(user_key)

        file_count = 0
        folder_count = 0
        total_size = 0

        for root, dirs, files in os.walk(user_dir):
            dirs[:] = [d for d in dirs if d not in HIDDEN_NAMES]

            folder_count += len(dirs)

            for file in files:
                path = Path(root) / file

                try:
                    total_size += path.stat().st_size
                except OSError:
                    pass

                file_count += 1

        return jsonify({
            "success": True,
            "user": user_key,
            "files": file_count,
            "folders": folder_count,
            "size": total_size,
            "running": is_running(user_key)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：Python構文チェック
# =========================

@app.route("/api/check", methods=["POST"])
def api_check():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()
    code = str(data.get("code", ""))

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    try:
        compile(code, "<editor>", "exec")

        return jsonify({
            "success": True,
            "message": "構文エラーはありません。"
        })

    except SyntaxError as e:
        return jsonify({
            "success": False,
            "line": e.lineno,
            "offset": e.offset,
            "message": e.msg
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })

# =========================
# API：環境情報
# =========================

@app.route("/api/system")
def api_system():
    token = request.args.get("token", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    try:
        import platform
        import psutil

        disk = shutil.disk_usage(BASE_DIR)

        return jsonify({
            "success": True,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_percent": psutil.cpu_percent(interval=0.2),
            "cpu_count": psutil.cpu_count(),
            "memory_total": psutil.virtual_memory().total,
            "memory_used": psutil.virtual_memory().used,
            "memory_percent": psutil.virtual_memory().percent,
            "disk_total": disk.total,
            "disk_used": disk.used,
            "disk_free": disk.free,
            "running": is_running(user_key)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# API：ファイル情報
# =========================

@app.route("/api/stat")
def api_stat():
    token = request.args.get("token", "").strip()
    relative_path = request.args.get("path", "").strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False
        }), 403

    try:
        path = safe_path(user_key, relative_path)

        if not path.exists():
            return jsonify({
                "success": False,
                "message": "存在しません。"
            }), 404

        stat = path.stat()

        return jsonify({
            "success": True,
            "name": path.name,
            "is_dir": path.is_dir(),
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500

# =========================
# API：プロセス終了
# =========================

@app.route("/api/kill", methods=["POST"])
def api_kill():
    data = request.get_json(silent=True) or {}

    token = str(data.get("token", "")).strip()

    user_key = validate_token(token)
    if not user_key:
        return jsonify({
            "success": False,
            "message": "Invalid token"
        }), 403

    process = running_processes.get(user_key)

    if process is None:
        return jsonify({
            "success": False,
            "message": "プロセスが見つかりません。"
        })

    try:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

        process_logs.pop(user_key, None)
        running_processes.pop(user_key, None)

        append_log(user_key, "プロセスを強制終了しました。")

        return jsonify({
            "success": True,
            "message": "強制終了しました。"
        })

    except Exception as e:
        append_log(user_key, traceback.format_exc())

        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


# =========================
# 404
# =========================

@app.errorhandler(404)
def error_404(error):
    return render_template(
        "error.html",
        code=404,
        message="ページが見つかりません。"
    ), 404


# =========================
# 500
# =========================

@app.errorhandler(500)
def error_500(error):
    return render_template(
        "error.html",
        code=500,
        message="サーバー内部でエラーが発生しました。"
    ), 500


# =========================
# 終了処理
# =========================

def shutdown_all_processes():
    """
    サーバー終了時に全Botを停止する
    """
    for user_key in list(running_processes.keys()):
        try:
            stop_process(user_key)
        except Exception:
            pass


def register_signal_handlers():
    """
    SIGINT / SIGTERM を受け取ったらBotを停止
    """
    def handler(signum, frame):
        shutdown_all_processes()
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
    except Exception:
        # Windowsなど一部環境では設定できない場合がある
        pass


# =========================
# 起動
# =========================

if __name__ == "__main__":
    register_signal_handlers()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    print("=" * 50)
    print("Bot Hosting Panel")
    print("=" * 50)
    print(f"Host : {host}")
    print(f"Port : {port}")
    print("=" * 50)

    try:
        app.run(
            host=host,
            port=port,
            debug=debug,
            threaded=True
        )
    finally:
        shutdown_all_processes()

