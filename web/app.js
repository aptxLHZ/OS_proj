// web/app.js - 处理前端交互

let currentLoggedUser = "guest"; // 记录当前登录用户

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
    
    let isRoot = await eel.gui_is_root()();
    document.getElementById("btn-admin-tools").style.display = isRoot ? "flex" : "none";

    if (result.success) {
        // 登录成功，隐藏登录屏幕，显示桌面与任务栏
        currentLoggedUser = result.username; // 更新当前登录用户
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
    bringToFront(win);
    loadFiles(); // 每次打开自动加载文件
});

// 2. 窗口右上角关闭按钮
document.getElementById("close-file-manager").addEventListener("click", function() {
    document.getElementById("win-file-manager").style.display = "none";
});

// 3. 核心：从 Python 内核拉取文件列表并渲染
async function loadFiles() {
    let fileGrid = document.getElementById("file-grid");
    fileGrid.innerHTML = "<div style='padding:20px; color:#aaa;'>🔄 正在读取内核数据...</div>";
    
    let result = await eel.gui_get_files()();
    
    // 💡 如果后端读取报错，直接在网格里把红色错误原因打印出来！
    if (!result || !result.success) {
        fileGrid.innerHTML = `<div style='color:#f44336; font-weight:bold; font-size:14px; padding: 20px;'>
            🚨 读取目录失败：<br><br>${result ? result.error : "未知后端通信错误"}
            </div>`;
        return;
    }
    
    let files = result.files;
    fileGrid.innerHTML = ""; // 正常则清空
    
    // 💡 核心修复：自动精准更新资源管理器的地址栏！
    document.getElementById("address-bar").innerText = `当前位置: ${result.current_path} (Inode ${result.current_ino})`;
    
    files.forEach(file => {
        if (file.name === ".trashinfo") return;

        let icon = "📄";
        if (file.name === ".trash") icon = "🗑️";
        else if (file.type === "dir") icon = "📁";
        else if (file.type === "link") icon = "🔗";

        let item = document.createElement("div");
        item.className = "file-item";
        item.innerHTML = `<div class="file-icon">${icon}</div><div class="file-name">${file.name}</div>`;
        
        // 双击事件
        item.addEventListener("dblclick", async function() {
            if (file.type === "dir" || file.type === "link") {
                let res = await eel.gui_chdir(file.name)();
                if (res.success) {
                    loadFiles(); 
                } else {
                    // 软链接如果是文件，尝试拉起记事本
                    let res2 = await eel.gui_read_file(file.name)();
                    if(res2.success) {
                        document.getElementById("editor-title").innerText = `📝 编辑 - ${file.name}`;
                        document.getElementById("editor-textarea").value = res2.content;
                        let win = document.getElementById("win-editor");
                        win.style.display = "flex";
                        bringToFront(win);
                    } else alert(res2.error);
                }
            } else {
                currentSelectedFile = file.name;
                currentFileType = file.type;
                document.getElementById("menu-open").click(); 
            }
        });
        
        // 💡 右键菜单绑定
        item.addEventListener("contextmenu", function(e) {
            e.preventDefault();
            currentSelectedFile = file.name;
            currentFileType = file.type;
            
            let isTrash = document.getElementById("address-bar").innerText.includes(".trash");
            document.getElementById("menu-restore").style.display = isTrash ? "block" : "none";
            document.getElementById("menu-hard-delete").style.display = isTrash ? "block" : "none";
            document.getElementById("menu-delete").style.display = isTrash ? "none" : "block";
            document.getElementById("menu-compress").style.display = isTrash ? "none" : "block";
            document.getElementById("menu-rename").style.display = isTrash ? "none" : "block";
            document.getElementById("menu-link").style.display = isTrash ? "none" : "block";

            contextMenu.style.top = e.clientY + "px";
            contextMenu.style.left = e.clientX + "px";
            contextMenu.style.display = "block";
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
    bringToFront(win);
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

// --- 🖱️ 右键菜单与记事本引擎 ---
let currentSelectedFile = null;
let currentFileType = null;

const contextMenu = document.getElementById("context-menu");

// 隐藏右键菜单 (全局点击隐藏)
document.addEventListener("click", () => contextMenu.style.display = "none");

// 绑定记事本关闭和拖拽
document.getElementById("close-editor").addEventListener("click", () => document.getElementById("win-editor").style.display = "none");
makeDraggable(document.getElementById("win-editor")); // 激活拖拽


// --- 右键菜单功能绑定 ---

// 1. 属性查询 (调用后端的 ls -l 过滤)
document.getElementById("menu-info").addEventListener("click", async function() {
    let result = await eel.gui_get_file_info(currentSelectedFile)();
    if (result.success) alert(`【属性详情】\n\n${result.info}`);
    else alert("查询失败: " + result.error);
});

// 2. 删除文件/目录
document.getElementById("menu-delete").addEventListener("click", async function() {
    if(confirm(`确定要把 '${currentSelectedFile}' 移入回收站吗？`)) {
        let cmd = currentFileType === "dir" ? "rmdir" : "delete";
        await eel.execute_cmd(`${cmd} ${currentSelectedFile}`)();
        loadFiles();
    }
});

// 3. 压缩 / 解压
document.getElementById("menu-compress").addEventListener("click", async function() {
    if(currentFileType === "dir") return alert("暂不支持直接压缩目录！");
    let action = confirm("点击[确定]进行压缩，点击[取消]尝试解压");
    let cmd = action ? "compress" : "decompress";
    let res = await eel.execute_cmd(`${cmd} ${currentSelectedFile}`)();
    alert(res);
    loadFiles();
});

// 4. 重命名
document.getElementById("menu-rename").addEventListener("click", async function() {
    let newName = prompt(`将 '${currentSelectedFile}' 重命名为:`);
    if(newName) {
        let res = await eel.execute_cmd(`rename ${currentSelectedFile} ${newName}`)();
        alert(res);
        loadFiles();
    }
});

// 5. 还原 (仅在回收站有效)
document.getElementById("menu-restore").addEventListener("click", async function() {
    let res = await eel.execute_cmd(`restore ${currentSelectedFile}`)();
    alert(res);
    loadFiles();
});

// 6. 打开 / 编辑 (文本编辑器)
document.getElementById("menu-open").addEventListener("click", async function() {
    if(currentFileType === "dir" || currentFileType === "link") {
        let result = await eel.gui_chdir(currentSelectedFile)();
        if(result.success) {
            loadFiles();
            updateAddressBar(currentSelectedFile, "DIR/LINK");
        } else {
            // 如果 chdir 失败，说明软链接指向的可能是普通文件，拉起记事本！
            let res2 = await eel.gui_read_file(currentSelectedFile)();
            if(res2.success) {
                document.getElementById("editor-title").innerText = `📝 编辑 - ${currentSelectedFile}`;
                document.getElementById("editor-textarea").value = res2.content;
                document.getElementById("win-editor").style.display = "flex";
                document.getElementById("win-editor").style.zIndex = ++maxZIndex;
            } else alert(res2.error);
        }
    } else {
        // 是文件，调用 Python 纯文本接口，拉起记事本
        let result = await eel.gui_read_file(currentSelectedFile)();
        if(result.success) {
            document.getElementById("editor-title").innerText = `📝 编辑 - ${currentSelectedFile}`;
            document.getElementById("editor-textarea").value = result.content;
            document.getElementById("win-editor").style.display = "flex";
            // 居中显示并置顶
            let win = document.getElementById("win-editor");
            win.style.top = "10%"; win.style.left = "20%";
            win.style.zIndex = ++maxZIndex;
        } else {
            alert("读取失败: " + result.error);
        }
    }
});

// 记事本保存按钮
document.getElementById("btn-editor-save").addEventListener("click", async function() {
    let content = document.getElementById("editor-textarea").value;
    let filename = document.getElementById("editor-title").innerText.replace("📝 编辑 - ", "");
    let result = await eel.gui_write_file(filename, content)();
    if(result.success) {
        alert("💾 文件保存成功！");
        loadFiles();
    } else {
        alert("保存失败: " + result.error);
    }
});


// --- 新增：新建文件按钮 ---
document.getElementById("btn-gui-create").addEventListener("click", async function() {
    let filename = prompt("请输入新建普通文件的名称:");
    if (filename) {
        let result = await eel.gui_create_file(filename.trim())();
        if (result.success) loadFiles();
        else alert("创建失败: " + result.error);
    }
});

// --- 新增：彻底物理删除 (菜单点击) ---
document.getElementById("menu-hard-delete").addEventListener("click", async function() {
    if(confirm(`🚨 警告：确定要彻底物理销毁 '${currentSelectedFile}' 吗？此操作不可逆！`)) {
        await eel.execute_cmd(`hard_delete ${currentSelectedFile}`)();
        loadFiles();
    }
});

// --- 新增：Shift + Delete 快捷键物理删除 ---
document.addEventListener('keydown', async function(e) {
    if (e.shiftKey && e.key === 'Delete' && currentSelectedFile) {
        if(confirm(`🚨 快捷键触发：确定要物理彻底删除 '${currentSelectedFile}' 吗？此操作无法恢复！`)) {
            await eel.execute_cmd(`hard_delete ${currentSelectedFile}`)();
            loadFiles();
        }
    }
});

// --- 新增：创建软/硬链接 ---
document.getElementById("menu-link").addEventListener("click", async function() {
    let type = prompt("请输入链接类型 (h:硬链接, s:软链接):", "h");
    if(!type) return;
    let linkName = prompt(`请为 '${currentSelectedFile}' 输入链接名称:`);
    if(linkName) {
        let cmd = type.toLowerCase() === 's' ? `ln -s ${currentSelectedFile} ${linkName}` : `ln ${currentSelectedFile} ${linkName}`;
        let res = await eel.execute_cmd(cmd)();
        alert(res);
        loadFiles();
    }
});


// --- ⚙️ 系统管理员面板 ---
document.getElementById("btn-admin-tools").addEventListener("click", () => {
    let win = document.getElementById("win-admin");
    win.style.display = "flex";
    bringToFront(win); 
    win.style.top = "15%"; 
    win.style.left = "10%";
});
document.getElementById("close-admin").addEventListener("click", () => document.getElementById("win-admin").style.display = "none");
makeDraggable(document.getElementById("win-admin"));

// 绑定五个破坏性指令，执行后通过弹窗返回结果
async function runAdminCmd(cmd, confirmMsg) {
    if (confirmMsg && !confirm(confirmMsg)) return;
    let res = await eel.execute_cmd(cmd)();
    alert("【执行结果】\n" + res);
}
// document.getElementById("btn-adm-status").addEventListener("click", () => runAdminCmd("status", null));
// document.getElementById("btn-adm-breakA").addEventListener("click", () => runAdminCmd("break A", "确定用铁锤砸坏物理磁盘A吗？"));
document.getElementById("btn-adm-repair").addEventListener("click", () => runAdminCmd("repair", "将从磁盘B全盘复制物理数据到磁盘A，确定吗？"));
document.getElementById("btn-adm-inject").addEventListener("click", () => runAdminCmd("inject_crash", "注入将导致下一次启动触发 fsck 自检修复，确定吗？"));
document.getElementById("btn-adm-format").addEventListener("click", async () => {
    // 💡 1. 在前端弹出精美的浏览器原生确认框
    if (confirm("🚨 🔥 极其严重的警告：\n\n该操作将物理抹除 A/B 双盘的所有数据并重启文件系统！\n你确定要执行这无法撤销的操作吗？")) {
        // 💡 2. 向后端发送带确认参数的指令
        let res = await eel.execute_cmd("format y")();
        alert("系统响应：\n" + res);
        // 💡 3. 执行完毕后，自动强制刷新资源管理器
        loadFiles();
    }
});

// --- 📊 动态物理盘块图谱 ---
document.getElementById("btn-disk-map").addEventListener("click", async () => {
    let win = document.getElementById("win-disk-map");
    win.style.display = "flex"; win.style.top = "10%"; win.style.left = "50%";
    bringToFront(win);
    
    // 渲染 512 个格子！
    let grid = document.getElementById("disk-grid-container");
    grid.innerHTML = "";
    let mapData = await eel.gui_get_disk_map()();
    
    for (let i = 0; i < 512; i++) {
        let box = document.createElement("div");
        box.className = "disk-block";
        if (mapData[i] === "boot") box.classList.add("block-boot");
        else if (mapData[i] === "super") box.classList.add("block-super");
        else if (mapData[i] === "inode") box.classList.add("block-inode");
        else if (mapData[i] === "data") box.classList.add("block-data");

        // 鼠标悬停显示这是第几个物理块
        box.title = `物理盘块 Block: ${i} | 状态: ${mapData[i]}`;

        // 💡 核心交互：单击物理块，调出 Hex Dump 审查数据！
        box.addEventListener("click", async () => {
            // 消除其他格子的闪烁高亮，给当前点击的格子加上霓虹紫描边
            document.querySelectorAll(".disk-block").forEach(b => b.style.outline = "none");
            box.style.outline = "1.5px solid #ff79c6";
            
            // 写入面板头部基本信息
            document.getElementById("inspect-no").innerText = i;
            let typeDesc = { "boot": "引导区 (Boot Sector)", "super": "超级块 (Super Block)", "inode": "i节点区 (Inode Table)", "data": "数据区 (Data Block)", "free": "空闲数据块" };
            document.getElementById("inspect-type").innerText = typeDesc[mapData[i]] || "未知";
            
            // 跨界调用 Python 底层物理读
            let res = await eel.gui_get_block_details(physNo, targetDisk)();
            // 💡 修复：无论好坏，都把真实的物理数据写到屏幕上！
            document.getElementById("inspect-hex").innerText = res.hex_dump || res.error;
            document.getElementById("inspect-text").innerText = res.text_preview || "解析失败";
            
            if (!res.success) {
                // 如果是坏道，用刺眼的红色显示这些真实的乱码！
                document.getElementById("inspect-hex").style.color = "#f44336"; 
                document.getElementById("inspect-text").style.color = "#f44336";
            } else {
                // 正常的块用健康的绿色和青色
                document.getElementById("inspect-hex").style.color = "#50fa7b"; 
                document.getElementById("inspect-text").style.color = "#8be9fd";
            }
        });

        grid.appendChild(box);
    }
});
document.getElementById("close-disk-map").addEventListener("click", () => document.getElementById("win-disk-map").style.display = "none");
makeDraggable(document.getElementById("win-disk-map"));

async function renderDiskMap() {
    let grid = document.getElementById("disk-grid-container");
    grid.innerHTML = "<div style='color:white; padding: 20px;'>加载中...</div>";
    
    let startBlock = parseInt(document.getElementById("map-page-start").value) || 0;
    let targetDisk = document.getElementById("map-disk-target").value; // "A" 或 "B"
    
    // 💡 动态更新窗口标题
    document.querySelector("#win-disk-map .window-title").innerText = `📊 物理盘块全景实时监控 - 磁盘 ${targetDisk} (Blocks ${startBlock} - ${startBlock+511})`;
    
    let res = await eel.gui_get_disk_map(startBlock, targetDisk)();
    let mapData = res.map;
    
    if (!mapData || !Array.isArray(mapData)) {
        mapData = Array(512).fill("free");
    }
    
    grid.innerHTML = "";
    let damageBtn = document.getElementById("btn-damage-selected-block");
    if (damageBtn) damageBtn.style.display = "none";
    
    for (let i = 0; i < 512; i++) {
        if (mapData[i] === "out_of_bounds") break;
        let physNo = startBlock + i;
        let box = document.createElement("div");
        box.className = "disk-block";
        
        if (mapData[i] === "boot") box.classList.add("block-boot");
        else if (mapData[i] === "super") box.classList.add("block-super");
        else if (mapData[i] === "inode") box.classList.add("block-inode");
        else if (mapData[i] === "data") box.classList.add("block-data");
        else if (mapData[i] === "damaged") box.classList.add("block-damaged");
        
        box.title = `磁盘 ${targetDisk} | Block: ${physNo}`;
        
        box.addEventListener("click", async () => {
            document.querySelectorAll(".disk-block").forEach(b => b.style.outline = "none");
            box.style.outline = "1.5px solid #ff79c6";
            box.style.outlineOffset = "-1px";
            
            document.getElementById("inspect-no").innerText = physNo;
            let typeDesc = { "boot": "引导区", "super": "超级块", "inode": "i节点区", "data": "数据区", "free": "空闲数据区", "damaged": "🚨 物理已损坏" };
            document.getElementById("inspect-type").innerText = typeDesc[mapData[i]] || "未知";
            
            let isRoot = (typeof currentLoggedUser !== 'undefined' && currentLoggedUser === "root");
            let canDamage = (physNo >= 2) && isRoot;
            if (damageBtn) {
                damageBtn.style.display = canDamage ? "block" : "none";
                damageBtn.innerText = `💥 物理砸坏 ${targetDisk} 盘此块`;
            }
            
            // 💡 上帝视角读取真实的物理数据！
            let detailRes = await eel.gui_get_block_details(physNo, targetDisk)();
            document.getElementById("inspect-hex").innerText = detailRes.hex_dump;
            document.getElementById("inspect-text").innerText = detailRes.text_preview;
            if(!detailRes.success) {
                document.getElementById("inspect-hex").style.color = "#f44336"; // 报错用红色
                document.getElementById("inspect-text").style.color = "#f44336";
            } else {
                document.getElementById("inspect-hex").style.color = "#50fa7b"; // 正常用绿色
                document.getElementById("inspect-text").style.color = "#8be9fd";
            }
        });
        
        grid.appendChild(box);
    }
}

// 💡 修复跳转与切换事件
document.getElementById("btn-map-go").addEventListener("click", renderDiskMap);
document.getElementById("map-page-start").addEventListener("keydown", (e) => { if(e.key === "Enter") renderDiskMap(); });
document.getElementById("map-disk-target").addEventListener("change", renderDiskMap);

// 💡 损坏按钮
document.getElementById("btn-damage-selected-block").addEventListener("click", async () => {
    let blockNo = parseInt(document.getElementById("inspect-no").innerText);
    let targetDisk = document.getElementById("map-disk-target").value;
    if (confirm(`🚨 物理砸坏警告：\n确定要砸坏磁盘 ${targetDisk} 的 Block ${blockNo} 吗？`)) {
        let result = await eel.gui_damage_block(blockNo, targetDisk)();
        if (result.success) {
            alert(`[+] 成功物理覆写损坏 Block ${blockNo}！`);
            renderDiskMap(); 
            // 💡 修复：强行重新模拟点击该物理块，让右侧瞬间读出我们刚才写入的 DEADBEEF 乱码！
            setTimeout(() => {
                let startBlock = parseInt(document.getElementById("map-page-start").value) || 0;
                let blocks = document.querySelectorAll(".disk-block");
                if(blocks[blockNo - startBlock]) blocks[blockNo - startBlock].click();
            }, 200);
        } else {
            alert("损坏注入失败: " + result.error);
        }
    }
});

// 绑定打开图谱的按钮
document.getElementById("btn-disk-map").addEventListener("click", () => {
    let win = document.getElementById("win-disk-map");
    win.style.display = "flex"; 
    win.style.top = "5%"; 
    win.style.left = "15%"; // 💡 默认居中偏左一点点
    renderDiskMap(); 
});

// 绑定图谱的 🔄 刷新按钮
document.getElementById("refresh-disk-map").addEventListener("click", () => {
    renderDiskMap();
});

let isMapMaximized = false;
let oldMapWidth, oldMapHeight, oldMapTop, oldMapLeft;

document.getElementById("max-disk-map").addEventListener("click", function() {
    let win = document.getElementById("win-disk-map");
    let gridContainer = document.getElementById("disk-grid-container");
    
    if (!isMapMaximized) {
        // 1. 存下当前的尺寸和坐标
        oldMapWidth = win.style.width;
        oldMapHeight = win.style.height;
        oldMapTop = win.style.top;
        oldMapLeft = win.style.left;
        
        // 2. 赋予其全屏覆盖样式 (95% 的网页宽高度)
        win.style.width = "95vw";
        win.style.height = "85vh";
        win.style.top = "5vh";
        win.style.left = "2.5vw";
        
        // 3. 将左侧格子容器高度同步撑高，保证大图谱极其饱满！
        gridContainer.style.maxHeight = "60vh";
        
        isMapMaximized = true;
        this.innerText = "🗗"; // 切换为还原图标
    } else {
        // 还原尺寸
        win.style.width = oldMapWidth;
        win.style.height = oldMapHeight;
        win.style.top = oldMapTop;
        win.style.left = oldMapLeft;
        
        gridContainer.style.maxHeight = "330px"; // 还原格子高度
        
        isMapMaximized = false;
        this.innerText = "🔲";
    }
});
