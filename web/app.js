// web/app.js - 处理前端交互

// 绑定登录按钮点击事件
document.getElementById("btn-login-submit").addEventListener("click", performLogin);

// 绑定回车键登录
document.addEventListener("keydown", function(event) {
    if (event.key === "Enter" && document.getElementById("login-screen").style.display !== "none") {
        performLogin();
    }
});

async function performLogin() {
    let user = document.getElementById("username").value.trim();
    let pass = document.getElementById("password").value;
    let errorElem = document.getElementById("login-error");
    
    if (!user || !pass) {
        errorElem.innerText = "用户名或密码不能为空！";
        errorElem.style.display = "block";
        return;
    }
    
    // 💡 核心跨界调用：调用 Python 中的 gui_login 接口
    let result = await eel.gui_login(user, pass)();
    
    if (result.success) {
        // 登录成功，隐藏登录屏幕，显示桌面与任务栏
        document.getElementById("login-screen").style.display = "none";
        document.getElementById("desktop").style.display = "flex";
        document.getElementById("taskbar").style.display = "flex";
        
        // 刷新内核看板数据
        updateKernelInfo(result.username);
    } else {
        // 登录失败，显示错误信息
        errorElem.innerText = result.error;
        errorElem.style.display = "block";
    }
}

// 绑定注销按钮
document.getElementById("btn-logout").addEventListener("click", async function() {
    let result = await eel.gui_logout()();
    if (result.success) {
        // 注销成功，重新显示登录屏，并清空输入框
        document.getElementById("login-screen").style.display = "flex";
        document.getElementById("desktop").style.display = "none";
        document.getElementById("taskbar").style.display = "none";
        document.getElementById("password").value = "";
        document.getElementById("login-error").style.display = "none";
    }
});

// 获取超级块数据的函数
async function updateKernelInfo(username) {
    document.getElementById("welcome-title").innerText = "欢迎进入 myOS, " + username + "!";
    let info = await eel.get_kernel_info()();
    document.getElementById("status-text").innerText = "内核连接成功！当前挂载信息: " + info;
}

// --- 📂 资源管理器交互逻辑 ---

// 1. 任务栏点击打开
document.getElementById("btn-file-manager").addEventListener("click", function() {
    let win = document.getElementById("win-file-manager");
    win.style.display = "flex";
    // 居中显示窗口
    win.style.top = "15%";
    win.style.left = "25%";
    loadFiles(); // 每次打开自动加载文件
});

// 2. 窗口右上角关闭按钮
document.getElementById("close-file-manager").addEventListener("click", function() {
    document.getElementById("win-file-manager").style.display = "none";
});

// 3. 核心：从 Python 内核拉取文件列表并渲染
async function loadFiles() {
    let fileGrid = document.getElementById("file-grid");
    fileGrid.innerHTML = "正在读取内核数据...";
    
    // 调用 Python 接口获取当前目录所有文件信息
    let files = await eel.gui_get_files()();
    fileGrid.innerHTML = ""; // 清空
    
    files.forEach(file => {
        // 过滤掉系统隐藏的垃圾箱和 trashinfo (保持桌面清爽)
        if (file.name === ".trashinfo") return;

        // 根据文件类型指定精美图标
        let icon = "📄";
        
        if (file.type === "dir") icon = "📁";
            if (file.name === ".trash") icon = "🗑️";
        else if (file.type === "link") icon = "🔗";

        let item = document.createElement("div");
        item.className = "file-item";
        item.innerHTML = `
            <div class="file-icon">${icon}</div>
            <div class="file-name">${file.name}</div>
        `;
        
        // 💡 核心交互：双击事件
        item.addEventListener("dblclick", async function() {
            if (file.type === "dir") {
                // 如果是文件夹，调用后台 cd 进去，并重新刷新列表！
                let result = await eel.gui_chdir(file.name)();
                if (result.success) {
                    loadFiles(); // 递归刷新
                    updateAddressBar(file.name, file.ino);
                }
            } else {
                alert(`这是普通文件 '${file.name}'，Inode号: ${file.ino}，大小: ${file.size}B。\n在下一个任务里，双击将直接弹出文本编辑器！`);
            }
        });
        
        fileGrid.appendChild(item);
    });
}

// 4. 返回上一级目录按钮
document.getElementById("btn-go-back").addEventListener("click", async function() {
    // 双击 ".." 目录项即代表返回上一级
    let result = await eel.gui_chdir("..")();
    if (result.success) {
        loadFiles();
        // 简单更新地址栏
        document.getElementById("address-bar").innerText = "当前位置: 返回上一级";
    }
});

// 5. 新建文件夹按钮
document.getElementById("btn-gui-mkdir").addEventListener("click", async function() {
    let dirname = prompt("请输入新建文件夹的名称:");
    if (dirname) {
        let result = await eel.gui_mkdir(dirname.trim())();
        if (result.success) {
            loadFiles(); // 刷新
        } else {
            alert("创建失败: " + result.error);
        }
    }
});

function updateAddressBar(name, ino) {
    document.getElementById("address-bar").innerText = `当前位置: ${name} (Inode ${ino})`;
}

// --- 💻 系统终端交互逻辑 ---

// 1. 任务栏点击打开
document.getElementById("btn-terminal").addEventListener("click", async function() {
    let win = document.getElementById("win-terminal");
    win.style.display = "flex";
    win.style.top = "20%";
    win.style.left = "30%";
    
    // 聚焦输入框并刷新提示符
    document.getElementById("terminal-input").focus();
    refreshTerminalPrompt();
});

// 2. 窗口关闭
document.getElementById("close-terminal").addEventListener("click", function() {
    document.getElementById("win-terminal").style.display = "none";
});

// 3. 动态刷新终端提示符
async function refreshTerminalPrompt() {
    let promptText = await eel.get_terminal_prompt()();
    document.getElementById("terminal-prompt").innerHTML = promptText + "&nbsp;";
}

// 4. 监听回车键发送命令
let commandHistory = []; // 存储历史命令的队列
let historyIndex = -1;   // 当前历史索引指针
document.getElementById("terminal-input").addEventListener("keydown", async function(event) {
    let inputElem = document.getElementById("terminal-input");
    // 💡 1. 拦截上方向键 (ArrowUp)
    if (event.key === "ArrowUp") {
        event.preventDefault(); // 阻止光标跳到开头的默认行为
        if (commandHistory.length > 0) {
            if (historyIndex === -1) historyIndex = commandHistory.length - 1;
            else if (historyIndex > 0) historyIndex--;
            inputElem.value = commandHistory[historyIndex];
        }
        return;
    }
    
    // 💡 2. 拦截下方向键 (ArrowDown)
    if (event.key === "ArrowDown") {
        event.preventDefault();
        if (historyIndex !== -1) {
            if (historyIndex < commandHistory.length - 1) {
                historyIndex++;
                inputElem.value = commandHistory[historyIndex];
            } else {
                historyIndex = -1;
                inputElem.value = ""; // 清空
            }
        }
        return;
    }

    if (event.key === "Tab") {
        event.preventDefault(); // 💡 极其重要：拦截并阻止浏览器的焦点切换默认行为！
        let val = inputElem.value;
        if (!val) return;
        
        // 调用 Python 后台自动补全
        let res = await eel.gui_autocomplete(val)();
        if (typeof res === "string") {
            inputElem.value = res; // 补全成功，更新文本框！
        } else if (res && res.matches) {
            // 💡 多个匹配项：模拟 Linux 双击 Tab，在屏幕上打印出所有的候选名字！
            let outputArea = document.getElementById("terminal-output");
            outputArea.innerHTML += `<div><span style="color: #ff79c6">候选匹配:</span> ${res.matches.join("   ")}</div>`;
            outputArea.scrollTop = outputArea.scrollHeight;
        }
        return;
    }

    if (event.key === "Enter") {
        let inputElem = document.getElementById("terminal-input");
        let cmdText = inputElem.value.trim();
        if (!cmdText) return;
        
        let outputArea = document.getElementById("terminal-output");
        let currentPrompt = document.getElementById("terminal-prompt").innerText;
        
        // 1) 在屏幕上打印出你刚才输入的这行命令
        outputArea.innerHTML += `<div><span style="color: #8be9fd">${currentPrompt}</span> ${cmdText}</div>`;
        inputElem.value = ""; // 清空输入框
        
        // 2) 💡 核心跨界调用：将命令发送给 Python 执行，并获取 Stdout 重定向回显！
        let stdout = await eel.execute_cmd(cmdText)();
        
        // 3) 将回显结果打印到屏幕上
        outputArea.innerHTML += `<div>${stdout.replace(/\n/g, "<br>")}</div>`;

        // 如果用户输入的是 exit
        if (cmdText === "exit") {
            eel.gui_exit()(); // 通知 Python 安全刷盘并关闭
            setTimeout(() => {
                window.close(); // 💡 强行关闭前端网页窗口！
            }, 300); // 留 300 毫秒让后端收尾
        }
        
        // 4) 滚动条自动滚到最底部
        outputArea.scrollTop = outputArea.scrollHeight;
        
        // 5) 💡 内核联动：更新提示符，并自动通知“资源管理器”刷新文件列表！
        await refreshTerminalPrompt();
        if (document.getElementById("win-file-manager").style.display !== "none") {
            loadFiles(); // 极速联动：如果资源管理器开着，自动刷新图标！
        }
        // 6) 将命令加入历史记录
        if (cmdText && (commandHistory.length === 0 || commandHistory[commandHistory.length - 1] !== cmdText)) {
            commandHistory.push(cmdText);
        }
        historyIndex = -1; // 归零指针
    }
});

// --- 窗口通用拖拽与点击置顶引擎 ---
let maxZIndex = 100;

function makeDraggable(win) {
    let header = win.querySelector(".window-header");
    if (!header) return;

    let posX = 0, posY = 0, mouseX = 0, mouseY = 0;
    header.onmousedown = dragMouseDown;

    // 点击窗口任意位置，使其置顶 (提高 z-index)
    win.addEventListener("mousedown", () => {
        maxZIndex++;
        win.style.zIndex = maxZIndex;
    });

    function dragMouseDown(e) {
        e = e || window.event;
        e.preventDefault();
        mouseX = e.clientX;
        mouseY = e.clientY;
        document.onmouseup = closeDragElement;
        document.onmousemove = elementDrag;
    }

    function elementDrag(e) {
        e = e || window.event;
        e.preventDefault();
        posX = mouseX - e.clientX;
        posY = mouseY - e.clientY;
        mouseX = e.clientX;
        mouseY = e.clientY;
        win.style.top = (win.offsetTop - posY) + "px";
        win.style.left = (win.offsetLeft - posX) + "px";
    }

    function closeDragElement() {
        document.onmouseup = null;
        document.onmousemove = null;
    }
}

// 自动使桌面上所有的窗口都支持拖拽
document.querySelectorAll(".window").forEach(makeDraggable);


