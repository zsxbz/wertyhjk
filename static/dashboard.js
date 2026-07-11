// =========================
// dashboard.js (1/3)
// =========================

let currentFile = "";

const editor = document.getElementById("editor");
const logArea = document.getElementById("logArea");
const runStatus = document.getElementById("runStatus");

// -------------------------
// JSON送信
// -------------------------

async function post(url, data) {
    const res = await fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(data)
    });

    return await res.json();
}

// -------------------------
// ファイル読み込み
// -------------------------

async function openFile(path) {

    const res = await fetch(
        `/api/file?token=${encodeURIComponent(token)}&path=${encodeURIComponent(path)}`
    );

    const data = await res.json();

    if (!data.success) {
        alert(data.message);
        return;
    }

    currentFile = path;
    editor.value = data.content;
}

// -------------------------
// ファイルクリック
// -------------------------

document.querySelectorAll(".tree-item").forEach(item => {

    item.onclick = () => {

        const path = item.dataset.path;

        openFile(path);

    };

});

// -------------------------
// 保存
// -------------------------

document.getElementById("saveBtn").onclick = async () => {

    if (!currentFile) {
        alert("ファイルを選択してください。");
        return;
    }

    const result = await post("/api/file", {

        token,

        path: currentFile,

        content: editor.value

    });

    alert(result.message);

};
// =========================
// dashboard.js (2/3)
// =========================

// -------------------------
// Bot起動
// -------------------------

document.getElementById("startBtn").onclick = async () => {

    const result = await post("/api/start", {
        token
    });

    alert(result.message);

    updateStatus();

};

// -------------------------
// Bot停止
// -------------------------

document.getElementById("stopBtn").onclick = async () => {

    const result = await post("/api/stop", {
        token
    });

    alert(result.message);

    updateStatus();

};

// -------------------------
// Bot再起動
// -------------------------

document.getElementById("restartBtn").onclick = async () => {

    const result = await post("/api/restart", {
        token
    });

    alert(result.message);

    updateStatus();

};

// -------------------------
// ZIPダウンロード
// -------------------------

document.getElementById("downloadBtn").onclick = () => {

    location.href =
        `/download?token=${encodeURIComponent(token)}`;

};

// -------------------------
// ステータス更新
// -------------------------

async function updateStatus() {

    const res = await fetch(
        `/api/status?token=${encodeURIComponent(token)}`
    );

    const data = await res.json();

    if (!data.success) return;

    runStatus.textContent =
        data.running
            ? "🟢 Running"
            : "🔴 Stopped";

}

// -------------------------
// ログ取得
// -------------------------

async function updateLog() {

    const res = await fetch(
        `/api/log?token=${encodeURIComponent(token)}`
    );

    const data = await res.json();

    if (!data.success) return;

    logArea.textContent = data.log;

    logArea.scrollTop = logArea.scrollHeight;

}
// =========================
// dashboard.js (3/3)
// =========================

// -------------------------
// ファイルツリー更新
// -------------------------

async function refreshTree() {

    const res = await fetch(
        `/api/tree?token=${encodeURIComponent(token)}`
    );

    const data = await res.json();

    if (!data.success) return;

    const tree = document.getElementById("fileTree");
    tree.innerHTML = "";

    function addItems(items, indent = 0) {
        for (const item of items) {
            const div = document.createElement("div");

            div.className = "tree-item";
            div.dataset.path = item.path;

            div.style.paddingLeft = (indent * 20 + 8) + "px";
            div.textContent = (item.is_dir ? "📁 " : "📄 ") + item.name;

            div.onclick = () => {
                if (!item.is_dir) {
                    openFile(item.path);
                }
            };

            tree.appendChild(div);

            if (item.is_dir && item.children) {
                addItems(item.children, indent + 1);
            }
        }
    }

    addItems(data.tree);
}

// -------------------------
// 定期更新
// -------------------------

setInterval(updateStatus, 3000);
setInterval(updateLog, 2000);
setInterval(refreshTree, 5000);

// -------------------------
// 初期化
// -------------------------

window.addEventListener("load", () => {
    updateStatus();
    updateLog();
    refreshTree();
});

// Ctrl + S で保存
document.addEventListener("keydown", async (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();

        if (!currentFile) return;

        const result = await post("/api/file", {
            token,
            path: currentFile,
            content: editor.value
        });

        if (!result.success) {
            alert(result.message);
        }
    }
});
