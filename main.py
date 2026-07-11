# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, send_from_directory, render_template
import os
import json
import subprocess
import shutil
import psutil
import time

app = Flask(__name__)

ROOT = "apps"
LOG_DIR = "logs"
DATA_DIR = "data"

os.makedirs(ROOT, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

SERVER_FILE = os.path.join(DATA_DIR, "servers.json")

if not os.path.exists(SERVER_FILE):
    with open(SERVER_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)


# 起動中プロセス
processes = {}


def safe_path(path):
    path = path.replace("\\", "/")
    path = os.path.normpath(
        os.path.join(ROOT, path)
    )

    if not path.startswith(
        os.path.abspath(ROOT)
    ):
        raise Exception("Invalid path")

    return path



# =====================
# Web公開
# =====================

@app.route("/<server>/<path:file>")
def public_file(server, file):

    return send_from_directory(
        os.path.join(ROOT, server),
        file
    )



# =====================
# 管理画面
# =====================

@app.route("/")
@app.route("/panel")
def panel():

    return render_template(
        "index.html"
    )



# =====================
# CPU RAM
# =====================

@app.route("/api/status")
def status():

    return jsonify({
        "cpu": psutil.cpu_percent(),
        "ram": psutil.virtual_memory().percent
    })



# =====================
# ファイル一覧
# =====================

@app.route("/api/files")
def files():

    path = request.args.get(
        "path",
        ""
    )

    target = safe_path(path)

    result=[]

    if os.path.exists(target):

        for name in os.listdir(target):

            full=os.path.join(
                target,
                name
            )

            result.append({
                "name":name,
                "folder":os.path.isdir(full)
            })

    return jsonify(result)



# =====================
# 読み込み
# =====================

@app.route("/api/read")
def read():

    path=safe_path(
        request.args["path"]
    )

    with open(
        path,
        encoding="utf-8"
    ) as f:

        return f.read()



# =====================
# 保存
# =====================

@app.route("/api/edit", methods=["POST"])
def edit():

    data=request.json

    path=safe_path(
        data["path"]
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            data["text"]
        )

    return "ok"



# =====================
# 削除
# =====================

@app.route("/api/delete", methods=["POST"])
def delete():

    path=safe_path(
        request.json["path"]
    )

    if os.path.isdir(path):
        shutil.rmtree(path)

    else:
        os.remove(path)

    return "ok"



# =====================
# 名前変更
# =====================

@app.route("/api/rename", methods=["POST"])
def rename():

    old=safe_path(
        request.json["path"]
    )

    new=os.path.join(
        os.path.dirname(old),
        request.json["name"]
    )

    os.rename(
        old,
        new
    )

    return "ok"



# =====================
# フォルダ作成
# =====================

@app.route("/api/mkdir", methods=["POST"])
def mkdir():

    path=safe_path(
        request.json["path"]
    )

    os.mkdir(
        os.path.join(
            path,
            request.json["name"]
        )
    )

    return "ok"



# =====================
# アップロード
# =====================

@app.route("/api/upload", methods=["POST"])
def upload():

    path=safe_path(
        request.form["path"]
    )

    file=request.files["file"]

    file.save(
        os.path.join(
            path,
            file.filename
        )
    )

    return "ok"



# =====================
# 起動
# =====================

@app.route("/api/start/<name>")
def start(name):

    file=os.path.join(
        ROOT,
        name,
        "main.py"
    )

    if not os.path.exists(file):
        return "main.py not found"


    log=open(
        os.path.join(
            LOG_DIR,
            name+".log"
        ),
        "a",
        encoding="utf-8"
    )


    p=subprocess.Popen(
        [
            "python",
            file
        ],
        stdout=log,
        stderr=log,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
    )


    processes[name]=p


    return "started"



# =====================
# 停止
# =====================

@app.route("/api/stop/<name>")
def stop(name):

    p=processes.get(name)

    if p:

        try:
            p.terminate()

        except:
            pass


    return "stopped"



# =====================
# 再起動
# =====================

@app.route("/api/restart/<name>")
def restart(name):

    stop(name)

    time.sleep(1)

    return start(name)



# =====================
# プロセス一覧
# =====================

@app.route("/api/processes")
def process_list():

    data=[]

    for name,p in processes.items():

        data.append({
            "name":name,
            "pid":p.pid,
            "running":p.poll() is None
        })


    return jsonify(data)



# =====================
# ログ
# =====================

@app.route("/api/log/<name>")
def log(name):

    file=os.path.join(
        LOG_DIR,
        name+".log"
    )


    if not os.path.exists(file):
        return ""


    with open(
        file,
        encoding="utf-8"
    ) as f:

        return f.read()[-10000:]



if __name__=="__main__":

    app.run(
        host="0.0.0.0",
        port=8000,
        debug=False
    )
