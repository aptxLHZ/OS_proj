# main.py - 模拟操作系统的交互式 Shell
import os
import sys
import time
import threading
from disk_core import sync_format_all
import disk_core
from kernel import format_root_dir, fsck, get_current_user, set_current_user
from api import (
    mkdir, rmdir, chdir, dir_list, create, delete, restore, hard_delete,
    open_file, close_file, write_file, read_file, show_disk_map,
    current_working_dir_inode, login, logout, rename,
    compress, decompress, ln, symlink
)
import getpass
import eel

open_fds = {} #记录当前的用户打开的文件句柄字典 {fd: filepath}
def inject_crash():
    """【黑客级物理注入】：精准注入 Inode 身份窃取故障"""
    global super_block_memory
    from disk_core import super_block_memory, read_block, write_block, BLOCKSIZ
    import struct
    
    # 💡 1. 精准锁定：获取内存栈顶（下一个即将被分配出去）的空闲 Inode 号！
    from disk_core import super_block_memory
    target_ino = super_block_memory['inode'][super_block_memory['ninode'] - 1]
    
    # 2. 找到根目录的空槽位
    parent_block = 34
    dir_data = bytearray(read_block(parent_block))
    offset = -1
    for i in range(0, BLOCKSIZ, 16):
        ino, _ = struct.unpack('H 14s', dir_data[i:i+16])
        if ino == 0:
            offset = i
            break
            
    if offset == -1:
        raise Exception("注入失败：根目录已满")
        
    # 3. 强行在根目录下写入 broken.txt，指向这个即将分配的 target_ino
    dir_data[offset:offset+16] = struct.pack('H 14s', target_ino, b"broken.txt")
    write_block(parent_block, dir_data)
    
    print(f"[!] 成功物理注入『Inode身份窃取』故障！")
    print(f"[!] 已在根目录写入 'broken.txt' (指向即将分配的 Inode {target_ino})。")
    print("[!] 请立即退出系统 ('exit')，关闭 fsck，然后重新进入系统见证灾难！")
    

def boot_login():
    """开机/注销引导登录屏 (强制身份认证)"""
    print("\n" + "="*50)
    print("   Welcome to Virtual OS (Python UNIX FS Simulator)   ")
    print("="*50)
    import getpass
    while True:
        username = input("myOS login: ").strip()
        if not username:
            continue
        password = getpass.getpass("Password: ")
        try:
            from api import login
            login(username, password)
            break # 登录成功，放行进入命令行 Shell
        except Exception as e:
            print(f"[!] {e}\n")
            
def daemon_flush_thread():
    """💡 模拟内核的 pdflush 线程：每 2 秒将内存超级块同步回物理磁盘"""
    while True:
        time.sleep(2)
        if disk_core.superblock_dirty:
            disk_core.save_superblock()
            disk_core.superblock_dirty = False
            # 打印一个隐蔽的调试信息，证明后台在自动刷盘
            print("\n[后台] 内存超级块已自动同步刷盘...")
            
def run_single_command(user_input):
    """单条命令执行器 (对标原 CLI 核心逻辑)"""
    global open_fds
    user_input = user_input.strip()
    if not user_input:
        return
    parts = user_input.split()
    cmd = parts[0]
    args = parts[1:]
    
    if cmd == "exit":
        print("[*] 正在安全关闭文件系统并退出...")
        # 退出前关闭所有打开的文件
        for fd in list(open_fds.keys()):
            close_file(fd)
        return "EXIT"
        
    elif cmd == "help":
        print("\n--- 📖 系统调用指令清单 ---")
        print("  ls / dir               : 列出当前工作目录内容")
        print("  ls -l / dir -l         : 查看详细属性(权限、属主、大小、物理块号)")
        print("  cd [path]              : 切换当前目录 (支持绝对/相对路径)")
        print("  mkdir [name]           : 在当前工作目录下创建子目录")
        print("  rmdir [name]           : 软删除子目录 (移入回收站)")
        print("  create [name]          : 在当前工作目录下创建普通文件")
        print("  open [path] [r/w]      : 打开指定文件并分配 fd (文件描述符)")
        print("  write [fd] [content]   : 往描述符 fd 写入文本 (光标自动累计追加)")
        print("  read [fd]              : 从描述符 fd 当前光标位置读出数据")
        print("  close [fd]             : 关闭指定文件描述符 fd")
        print("  delete [name]          : 软删除普通文件 (移入回收站)")
        print("  restore [name]         : 自动从回收站将文件/目录恢复至其原路径")
        print("  hard_delete [name]     : 彻底物理删除：递减链接计数，归零时才物理释放")
        print("  ln [src] [link]        : 创建硬链接：使新名字指向同一个物理 Inode 号")
        print("  ln -s [src] [link]     : 创建符号链接(软链接)：保存指向源文件的路径")
        print("  rename [old] [new]     : 将当前目录下的文件/目录重命名(防重名)")
        print("  map                    : 查看物理盘块状态图谱 (支持参数 map [start] [len])")
        print("  format                 : (限管理员) 物理重新初始化并清空磁盘")
        print("  exit                   : 安全退出系统\n")
        print("\n-------------------------")
        
    elif cmd in ["ls", "dir"]:
        # 💡 支持传入参数 -l 展示详细图谱！ (如输入 ls -l)
        if args and args[0] == "-l":
            dir_list(detail=True)
        else:
            dir_list(detail=False)
            
    elif cmd == "rename":
        if len(args) < 2: print("用法: rename [原名字] [新名字]"); return
        # 默认在当前工作目录进行重命名
        rename(".", args[0], args[1])
        
    elif cmd == "cd":
        if not args: print("用法: cd [path]"); return
        chdir(args[0])
        
    elif cmd == "mkdir":
        if not args: print("用法: mkdir [dirname]"); return
        # 默认在当前目录下创建，使用相对路径机制
        mkdir(".", args[0])
        
    elif cmd == "rmdir":
        if not args: print("用法: rmdir [dirname]"); return
        rmdir(".", args[0])
        
    elif cmd == "create":
        if not args: print("用法: create [filename]"); return
        create(".", args[0])
        
    elif cmd == "open":
        if len(args) < 2: print("用法: open [path] [r/w]"); return
        fd = open_file(args[0], args[1])
        open_fds[fd] = args[0]
        
    elif cmd == "write":
        if len(args) < 2: print("用法: write [fd] [content]"); return
        fd = int(args[0])
        content = " ".join(args[1:]) # 支持写入空格空格的句子
        write_file(fd, content)
        
    elif cmd == "read":
        if not args: print("用法: read [fd]"); return
        fd = int(args[0])
        text = read_file(fd)
        print(f"--- 读取 fd={fd} 内容 ---\n{text}\n----------------------")
        
    elif cmd == "close":
        if not args: print("用法: close [fd]"); return
        fd = int(args[0])
        close_file(fd)
        if fd in open_fds: del open_fds[fd]
        
    elif cmd == "delete":
        if not args: print("用法: delete [name]"); return
        delete(".", args[0])
        
    elif cmd == "restore":
        if not args: print("用法: restore [name]"); return # 升级后用户只需要提供文件名！
        restore(args[0])
        
    elif cmd == "hard_delete":
        if not args: print("用法: hard_delete [name]"); return
        hard_delete(".", args[0])
    
    elif cmd == "map":
        if len(args) == 0:
            show_disk_map(0, 100) # 默认显示前 100 块
        elif len(args) == 1:
            show_disk_map(int(args[0]), 100) # 查看指定块开始的 100 块 (例如: map 80)
        elif len(args) >= 2:
            show_disk_map(int(args[0]), int(args[1])) # 查看指定范围 (例如: map 80 40)
        
    elif cmd == "format":
        uid, _ = get_current_user()
        if uid != 1:
            print("[!] 权限拒绝：只有系统管理员 root 才能执行格式化磁盘操作！")
            return
        # 💡 核心修复：不再使用阻塞的 input()，改为检查命令行参数
        # 这种设计模仿了 Linux 的 'rm -y' 强制执行逻辑
        if args and args[0].lower() == 'y':
            sync_format_all()
            format_root_dir()
            mkdir("/", ".trash")
            print("[+] 物理格式化成功！整个文件系统已重置。")
        else:
            print("[?] 确认：此操作将抹去所有数据！若确定，请输入 'format y'")
    
    elif cmd == "login":
        if not args: 
            print("用法: login [用户名]")
            return
        username = args[0]
        # 像 Linux 一样安全输入密码 (终端不显示输入痕迹)
        password = getpass.getpass("Password: ") 
        login(username, password)
        
    elif cmd == "logout":
        logout()
        #注销后重新拉起登录引导
        boot_login()
        
    elif cmd == "compress":
        if not args: print("用法: compress [path]"); return
        # 默认在当前工作目录进行压缩
        compress(args[0])
        
    elif cmd == "decompress":
        if not args: print("用法: decompress [path]"); return
        # 默认在当前工作目录进行解压
        decompress(args[0]) 
        
    elif cmd == "break":
        if not args: print("用法: break [A/B] (模拟砸坏某块物理盘)"); return
        target = args[0].upper()
        if target == "A":
            disk_core.disk_a_healthy = False
            print("[!] 警告：你故意用铁锤砸坏了物理磁盘 A！磁盘 A 已强制下线。")
        elif target == "B":
            disk_core.disk_b_healthy = False
            print("[!] 警告：你故意用铁锤砸坏了物理磁盘 B！磁盘 B 已强制下线。")
        else:
            print("[!] 未知目标，请输入 A 或 B")
            
    elif cmd == "repair":
        # 💡 调用物理重构
        try:
            disk_core.reconstruct_disk_a_from_b()
        except Exception as e:
            print(f"[!] 修复失败: {e}")
            
    elif cmd == "status":
        # 查看两块物理磁盘的健康状况
        status_a = "🟢 健康" if disk_core.disk_a_healthy else "🔴 故障/损坏"
        status_b = "🟢 健康" if disk_core.disk_b_healthy else "🔴 故障/损坏"
        print("\n--- 💾 RAID-1 物理磁盘状态报告 ---")
        print(f"  磁盘 A (data/disk_A.bin): {status_a}")
        print(f"  磁盘 B (data/disk_B.bin): {status_b}")
        print("----------------------------------\n")
        
    elif cmd == "inject_crash":
        inject_crash()
        
    elif cmd == "ln":
        # 支持软硬链接
        if len(args) < 2: print("用法: ln [源路径] [新链接名] 或 ln -s [源路径] [新链接名]"); return
        if args[0] == "-s":
            if len(args) < 3: print("用法: ln -s [源路径] [新链接名]"); return
            symlink(args[1], args[2])
        else:
            ln(args[0], args[1])
            
    else:
        print(f"[!] 未知指令: {cmd}。输入 'help' 获取命令帮助。")
    
    
def start_shell():
    print("\n" + "="*50)
    print("   Welcome to Virtual OS (Python UNIX FS Simulator)   ")
    print("   输入 'help' 获取所有系统调用指令清单")
    print("="*50)
    
    while True:
        try:
            # 动态获取当前工作目录的 Inode 提示符
            import api 
            _, user_name = get_current_user()
            prompt = f"{user_name}@myOS:[Inode {api.current_working_dir_inode}]$ "
            user_input = input(prompt).strip()
            signal = run_single_command(user_input)
            if signal == "EXIT":
                break

        except Exception as e:
            print(f"[!] 发生错误: {e}")

import io
@eel.expose
def execute_cmd(user_input):
    """【Eel 魔法接口】：供网页终端调用。拦截所有物理 print 字符，并以纯文本形式返回前端！"""
    old_stdout = sys.stdout
    # 建立内存缓冲区，重定向标准输出
    redirected_output = sys.stdout = io.StringIO()
    try:
        run_single_command(user_input)
    except Exception as e:
        print(f"[!] 发生错误: {e}")
    finally:
        # 恢复标准物理输出
        sys.stdout = old_stdout
        
    # 将截获的控制台打印字符返回给前端网页！
    return redirected_output.getvalue()

@eel.expose
def gui_login(username, password):
    """供前端调用的安全登录接口"""
    try:
        from api import login
        login(username, password)
        return {"success": True, "username": username}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def gui_logout():
    """供前端调用的安全注销接口"""
    try:
        from api import logout
        logout()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
@eel.expose
def get_kernel_info():
    from disk_core import super_block_memory
    return f"空闲盘块={super_block_memory['nfree']}, 空闲i节点={super_block_memory['ninode']}"

@eel.expose
def gui_get_files():
    """获取当前工作目录的文件列表 (返回前端可直接渲染的 JSON 数组)"""
    import struct
    import api
    from disk_core import read_block, BLOCKSIZ
    from kernel import get_inode
    
    current_ino = api.current_working_dir_inode
    inode_info = get_inode(current_ino)
    block_no = inode_info[5] 
    dir_data = read_block(block_no)
    
    files = []
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        if ino != 0:
            name_str = name.decode('utf-8').strip('\x00')
            item_info = get_inode(ino)
            mode = item_info[0]
            size = item_info[4]
            owner_uid = item_info[2]
            
            # 用户名映射
            if owner_uid == 1: owner_name = "root"
            elif owner_uid == 99: owner_name = "guest"
            else: owner_name = f"usr{owner_uid-1}"
            
            files.append({
                "ino": ino,
                "name": name_str,
                "type": "dir" if mode == 1 else ("file" if mode == 2 else "link"),
                "size": size,
                "owner": owner_name
            })
    return files

@eel.expose
def gui_chdir(dirname):
    """供前端调用的切换目录接口"""
    try:
        from api import chdir
        chdir(dirname)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def gui_mkdir(dirname):
    """供前端调用的新建目录接口"""
    try:
        from api import mkdir
        mkdir(".", dirname) # 默认在当前目录下创建
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def get_terminal_prompt():
    """供前端终端调用：动态获取当前的终端提示符 (如 root@myOS:[Inode 1]$)"""
    import api
    _, user_name = get_current_user()
    return f"{user_name}@myOS:[Inode {api.current_working_dir_inode}]$ "

@eel.expose
def gui_exit():
    """供前端调用：彻底物理安全关闭整个 Python 后端进程"""
    print("[*] 正在安全释放双盘物理驱动器...")
    import os
    import threading
    # 延迟 0.2 秒退出，保证前端网页能正常接收到最后一包响应数据
    threading.Timer(0.2, lambda: os._exit(0)).start()
    
def start_gui():
    """启动 Web OS 桌面"""
    print("[*] 正在启动 myOS 图形化桌面引擎...")
    # 指定前端资源文件夹
    eel.init('web')
    # 弹出一个 1024x768 的窗口，并禁用浏览器默认的控制台等特性
    eel.start('index.html', size=(1024, 768), mode='chrome', port=0)
    
@eel.expose
def gui_autocomplete(user_input):
    """【智能 Tab 补全】：支持绝对/相对路径及目录、文件的自动检索补全"""
    if not user_input or user_input.endswith(" "):
        return user_input
        
    parts = user_input.split()
    if len(parts) == 0:
        return user_input
        
    last_part = parts[-1] # 提取当前正在输入的最后一个路径/参数
    
    # 解析出父目录与待补全的前缀
    if "/" in last_part:
        parent_path = "/".join(last_part.split("/")[:-1])
        if not parent_path: parent_path = "/"
        prefix = last_part.split("/")[-1]
    else:
        parent_path = "."
        prefix = last_part
        
    try:
        from api import namei, get_inode, read_block, BLOCKSIZ
        import struct
        parent_ino = namei(parent_path)
        inode_info = get_inode(parent_ino)
        dir_data = read_block(inode_info[5])
        
        # 扫描该目录下所有的候选项
        matches = []
        for i in range(0, BLOCKSIZ, 16):
            ino, name = struct.unpack('H 14s', dir_data[i:i+16])
            if ino != 0:
                name_str = name.decode('utf-8').strip('\x00')
                if name_str in [".", "..", ".trash", ".trashinfo"]:
                    continue
                if name_str.startswith(prefix):
                    matches.append(name_str)
                    
        # 物理判定与组装
        if len(matches) == 1:
            # 💡 唯一匹配，执行补全！并在末尾自动加空格，方便用户接着输入
            completed = matches[0]
            if parent_path == ".":
                parts[-1] = completed
            elif parent_path == "/":
                parts[-1] = "/" + completed
            else:
                parts[-1] = parent_path + "/" + completed
            return " ".join(parts) + " "
        elif len(matches) > 1:
            # 💡 多个匹配，返回列表让前端进行打印提示
            return {"matches": matches, "current": user_input}
    except Exception:
        pass
        
    return user_input

@eel.expose
def gui_read_file(filename):
    """供前端 GUI 调用的纯文本读取"""
    try:
        from api import open_file, read_file, close_file
        fd = open_file(filename, "r")
        text = read_file(fd)
        close_file(fd)
        return {"success": True, "content": text}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def gui_write_file(filename, content):
    """供前端 GUI 调用的纯文本写入"""
    try:
        from api import open_file, write_file, close_file
        fd = open_file(filename, "w")
        write_file(fd, content)
        close_file(fd)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def gui_get_file_info(filename):
    """专门获取指定单个文件的详细属性"""
    try:
        from api import namei, get_inode
        ino = namei(filename)
        item_info = get_inode(ino)
        mode = item_info[0]
        
        perm_str = "d" if mode == 1 else ("l" if mode == 4 else "-")
        perm_str += "rwxr-xr-x" if mode == 1 else "rw-r--r--"
        
        owner_uid = item_info[2]
        owner_name = "root" if owner_uid == 1 else ("guest" if owner_uid == 99 else f"usr{owner_uid-1}")
        
        info_str = f"📁 名称: {filename}\n🔑 权限: {perm_str}\n👤 属主: {owner_name}\n💾 大小: {item_info[4]} B\n📍 Inode: {ino}\n📦 物理首块: {item_info[5]}\n🔗 硬链接数: {item_info[1]}"
        return {"success": True, "info": info_str}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def gui_is_root():
    """判断当前登录用户是否为 root，用于前端显示管理员菜单"""
    from kernel import get_current_user
    uid, _ = get_current_user()
    return uid == 1

@eel.expose
def gui_create_file(filename):
    """前端新建文件接口"""
    try:
        from api import create
        create(".", filename)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def gui_get_disk_map(start_block=0, target_disk="A"):
    """【高级多级索引自检测版】：获取指定磁盘前 512 个物理盘块的真实占用状态"""
    try: start_block = int(start_block)
    except: start_block = 0
        
    total_visual_blocks = 512
    disk_map = ["free"] * total_visual_blocks
    
    # 1. 标记系统保留区
    for i in range(total_visual_blocks):
        phys_no = start_block + i
        if phys_no == 0: disk_map[i] = "boot"
        elif phys_no == 1: disk_map[i] = "super"
        elif 2 <= phys_no <= 33: disk_map[i] = "inode"
        
    # 2. 💡 深度核心重构：扫描所有 512 个 Inode，进行直接/间接物理地址多层扫描
    try:
        from kernel import get_inode
        from disk_core import read_block, BLOCKSIZ
        import struct
        
        for ino in range(512):
            inode_info = get_inode(ino)
            mode = inode_info[0]
            if mode != 0: # Inode 处于分配状态
                # a. 扫描直接寻址区 addr[0] ~ addr[7] (元组索引 5 到 12)
                for block in inode_info[5:13]:
                    if block != 0 and start_block <= block < start_block + total_visual_blocks:
                        disk_map[block - start_block] = "data"
                        
                # b. 扫描一次间接寻址区 addr[8] (元组索引 13)
                ind1_block = inode_info[13]
                if ind1_block != 0:
                    if start_block <= ind1_block < start_block + total_visual_blocks:
                        disk_map[ind1_block - start_block] = "data" # 标记间址块本身
                    # 读出一次间址块，扫描其内部记录的 256 个子盘块
                    try:
                        ind1_data = read_block(ind1_block)
                        for j in range(0, BLOCKSIZ, 2):
                            sub_block = struct.unpack('H', ind1_data[j:j+2])[0]
                            if sub_block != 0 and start_block <= sub_block < start_block + total_visual_blocks:
                                disk_map[sub_block - start_block] = "data"
                    except Exception: pass
                    
                # c. 扫描二次间接寻址区 addr[9] (元组索引 14)
                ind2_block = inode_info[14]
                if ind2_block != 0:
                    if start_block <= ind2_block < start_block + total_visual_blocks:
                        disk_map[ind2_block - start_block] = "data" # 标记二次间址块本身
                    # 读出二次间址块，遍历里面的一级子间址指针
                    try:
                        ind2_data = read_block(ind2_block)
                        for j in range(0, BLOCKSIZ, 2):
                            sub_ind1 = struct.unpack('H', ind2_data[j:j+2])[0]
                            if sub_ind1 != 0:
                                if start_block <= sub_ind1 < start_block + total_visual_blocks:
                                    disk_map[sub_ind1 - start_block] = "data" # 标记一级子间址块
                                # 深度递归读取数据块
                                try:
                                    sub_ind1_data = read_block(sub_ind1)
                                    for k in range(0, BLOCKSIZ, 2):
                                        sub_sub_block = struct.unpack('H', sub_ind1_data[k:k+2])[0]
                                        if sub_sub_block != 0 and start_block <= sub_sub_block < start_block + total_visual_blocks:
                                            disk_map[sub_sub_block - start_block] = "data"
                                except Exception: pass
                    except Exception: pass
    except Exception: pass
        
    # 3. 根据查看的是 A 盘还是 B 盘，精准渲染损坏坏道！
    try:
        import disk_core
        damaged_set = disk_core.damaged_blocks_a if target_disk == "A" else getattr(disk_core, "damaged_blocks_b", set())
        for block in damaged_set:
            if start_block <= block < start_block + total_visual_blocks:
                disk_map[block - start_block] = "damaged"
    except Exception: pass
        
    return {"map": disk_map, "start": start_block}

@eel.expose
def gui_damage_block(block_no, target_disk="A"):
    """【真物理坏道注入】：直接往真实的 bin 文件里覆写死机乱码！绝非前端把戏！"""
    try:
        from kernel import get_current_user
        uid, _ = get_current_user()
        if uid != 1: raise Exception("权限拒绝：只有系统管理员 root 才能向介质注入坏道！")
            
        import disk_core
        from disk_core import DISK_A, DISK_B, BLOCKSIZ
        block_no = int(block_no)
        
        if not hasattr(disk_core, "damaged_blocks_b"): disk_core.damaged_blocks_b = set()
        
        # 1. 记录坏道标记（用于图谱变红拦截）
        if target_disk == "A": disk_core.damaged_blocks_a.add(block_no)
        else: disk_core.damaged_blocks_b.add(block_no)
        
        # 2. 💥 【真·物理破坏】：往真实的磁盘文件中写入 512 字节的 "DEADBEEF" 乱码！
        disk_file = DISK_A if target_disk == "A" else DISK_B
        with open(disk_file, "r+b") as f:
            f.seek(block_no * BLOCKSIZ)
            # DEADBEEF 占用 8 字节，乘 64 刚好 512 字节
            f.write(b"DEADBEEF" * 64) 
            
        print(f"[!] 物理灾难：已将磁盘 {target_disk} 的 {block_no} 块彻底物理覆写损毁！")
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@eel.expose
def gui_get_block_details(block_no, target_disk="A"):
    """💡 上帝视角：强制读取指定物理文件，展示真实的十六进制数据！绝不用假数据骗人！"""
    try:
        from disk_core import DISK_A, DISK_B, BLOCKSIZ
        import disk_core
        block_no = int(block_no)
        
        # 1. 绕过容错，直接去指定的真实物理文件里读
        # 因为我们在 gui_damage_block 里确实覆写了 DEADBEEF，这里必然能读出 DEADBEEF
        disk_file = DISK_A if target_disk == "A" else DISK_B
        with open(disk_file, "rb") as f:
            f.seek(block_no * BLOCKSIZ)
            data = f.read(BLOCKSIZ)
            
        # 2. 原汁原味的 Hex Dump 格式化
        hex_lines = []
        for i in range(0, BLOCKSIZ, 16):
            chunk = data[i:i+16]
            hex_str = " ".join(f"{b:02x}" for b in chunk)
            ascii_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            hex_lines.append(f"{i:04x}  {hex_str:<47}  |{ascii_str}|")
            
        try:
            # errors='replace' 可以防止遇到乱码时 decode 崩溃，强行展示乱码字符
            text_preview = data.decode('utf-8', errors='replace').strip('\x00')
            if not text_preview: text_preview = "[块内容为空闲或全零]"
        except Exception:
            text_preview = "[二进制/非文本数据，无法解析]"
            
        # 3. 查一下坏道名单，仅仅是为了告诉前端用“红色”显示，数据依然如实返回！
        damaged_set = disk_core.damaged_blocks_a if target_disk == "A" else getattr(disk_core, "damaged_blocks_b", set())
        is_damaged = block_no in damaged_set
        
        return {
            "success": not is_damaged, # 如果损坏，传回 False 告诉前端标红
            "hex_dump": "\n".join(hex_lines),
            "text_preview": text_preview[:200]
        }
    except Exception as e:
        return {"success": False, "error": str(e), "hex_dump": "读取失败", "text_preview": "读取失败"}
    

# 格式化 = 物理清零 + 逻辑重建

if __name__ == "__main__":
    # 如果 data/ 目录下文件坏了或者没有，自动执行初始化
    from disk_core import DISK_A, DISK_B, load_superblock, save_superblock
    if not os.path.exists(DISK_A) or not os.path.exists(DISK_B):
        sync_format_all()
        format_root_dir()
        mkdir("/", ".trash")
    else:
        load_superblock()
        # 开机自检并修复！
        fsck() 
        
    # 启动 2 秒延迟刷盘守护线程！
    t = threading.Thread(target=daemon_flush_thread, daemon=True)
    t.start()
    
    # #命令行
    # # 1. 引导开机登录
    # boot_login()
    # # 2. 验证通过，进入命令行Shell
    # start_shell()
    
    #可视化
    start_gui()