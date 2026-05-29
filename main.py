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
    compress, decompress
)
import getpass
import eel

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

def start_shell():
    print("\n" + "="*50)
    print("   Welcome to Virtual OS (Python UNIX FS Simulator)   ")
    print("   输入 'help' 获取所有系统调用指令清单")
    print("="*50)
    
    # 记录当前的用户打开的文件句柄字典 {fd: filepath}
    open_fds = {}
    
    while True:
        try:
            # 动态获取当前工作目录的 Inode 提示符
            import api 
            _, user_name = get_current_user()
            prompt = f"{user_name}@myOS:[Inode {api.current_working_dir_inode}]$ "
            
            user_input = input(prompt).strip()
            if not user_input:
                continue
                
            parts = user_input.split()
            cmd = parts[0]
            args = parts[1:]
            
            if cmd == "exit":
                print("[*] 正在安全关闭文件系统并退出...")
                # 退出前关闭所有打开的文件
                for fd in list(open_fds.keys()):
                    close_file(fd)
                break
                
            elif cmd == "help":
                print("\n--- 系统调用指令清单 ---")
                print("  ls / dir               : 列出当前工作目录内容")
                print("  ls -l / dir -l         : 查看详细属性(权限、属主、大小、物理块号)")
                print("  cd [path]              : 切换当前目录 (支持绝对/相对路径)")
                print("  mkdir [name]           : 在当前工作目录下创建子目录")
                print("  rmdir [name]           : 软删除当前工作目录下的子目录 (移入回收站)")
                print("  create [name]          : 在当前工作目录下创建普通文件")
                print("  open [path] [r/w]      : 打开指定文件并分配 fd (文件描述符)")
                print("  write [fd] [content]   : 往描述符 fd 写入文本 (光标自动累计追加)")
                print("  read [fd]              : 读出描述符 fd 当前光标后的所有文本数据")
                print("  close [fd]             : 关闭指定描述符 fd 并安全写回磁盘")
                print("  delete [name]          : 软删除当前工作目录下的普通文件 (移入回收站)")
                print("  restore [name]         : 自动从回收站将文件/目录恢复至其原绝对路径")
                print("  hard_delete [name]     : 彻底物理删除当前目录/回收站下的文件或目录")
                print("  rename [old] [new]     : 将当前目录下的文件/目录重命名(防重名)")
                print("  map                    : 查看物理盘块状态图谱 (支持参数 map [start] [len])")
                print("  format                 : (限管理员) 物理重新初始化并清空磁盘")
                print("  exit                   : 安全退出系统\n")
                
            elif cmd in ["ls", "dir"]:
                # 💡 支持传入参数 -l 展示详细图谱！ (如输入 ls -l)
                if args and args[0] == "-l":
                    dir_list(detail=True)
                else:
                    dir_list(detail=False)
                    
            elif cmd == "rename":
                if len(args) < 2: print("用法: rename [原名字] [新名字]"); continue
                # 默认在当前工作目录进行重命名
                rename(".", args[0], args[1])
                
            elif cmd == "cd":
                if not args: print("用法: cd [path]"); continue
                chdir(args[0])
                
            elif cmd == "mkdir":
                if not args: print("用法: mkdir [dirname]"); continue
                # 默认在当前目录下创建，使用相对路径机制
                mkdir(".", args[0])
                
            elif cmd == "rmdir":
                if not args: print("用法: rmdir [dirname]"); continue
                rmdir(".", args[0])
                
            elif cmd == "create":
                if not args: print("用法: create [filename]"); continue
                create(".", args[0])
                
            elif cmd == "open":
                if len(args) < 2: print("用法: open [path] [r/w]"); continue
                fd = open_file(args[0], args[1])
                open_fds[fd] = args[0]
                
            elif cmd == "write":
                if len(args) < 2: print("用法: write [fd] [content]"); continue
                fd = int(args[0])
                content = " ".join(args[1:]) # 支持写入空格空格的句子
                write_file(fd, content)
                
            elif cmd == "read":
                if not args: print("用法: read [fd]"); continue
                fd = int(args[0])
                text = read_file(fd)
                print(f"--- 读取 fd={fd} 内容 ---\n{text}\n----------------------")
                
            elif cmd == "close":
                if not args: print("用法: close [fd]"); continue
                fd = int(args[0])
                close_file(fd)
                if fd in open_fds: del open_fds[fd]
                
            elif cmd == "delete":
                if not args: print("用法: delete [name]"); continue
                delete(".", args[0])
                
            elif cmd == "restore":
                if not args: print("用法: restore [name]"); continue # 升级后用户只需要提供文件名！
                restore(args[0])
                
            elif cmd == "hard_delete":
                if not args: print("用法: hard_delete [name]"); continue
                hard_delete(".", args[0])
            
            elif cmd == "map":
                if len(args) == 0:
                    show_disk_map(0, 100) # 默认显示前 100 块
                elif len(args) == 1:
                    show_disk_map(int(args[0]), 100) # 查看指定块开始的 100 块 (例如: map 80)
                elif len(args) >= 2:
                    show_disk_map(int(args[0]), int(args[1])) # 查看指定范围 (例如: map 80 40)
                
            elif cmd == "format":
                # 安全特权校验：非 root 用户直接拦截
                uid, _ = get_current_user()
                if uid != 1:
                    print("[!] 权限拒绝：只有系统管理员 root 才能执行格式化磁盘操作！")
                    continue
                
                confirm = input("[!] 此操作会抹去 A/B 盘所有数据，确定格式化吗？(y/n): ").strip().lower()
                if confirm == 'y':
                    sync_format_all()
                    format_root_dir()
                    mkdir("/", ".trash")
            
            elif cmd == "login":
                if not args: 
                    print("用法: login [用户名]")
                    continue
                username = args[0]
                # 像 Linux 一样安全输入密码 (终端不显示输入痕迹)
                password = getpass.getpass("Password: ") 
                login(username, password)
                
            elif cmd == "logout":
                logout()
                #注销后重新拉起登录引导
                boot_login()
                
            elif cmd == "compress":
                if not args: print("用法: compress [path]"); continue
                # 默认在当前工作目录进行压缩
                compress(args[0])
                
            elif cmd == "decompress":
                if not args: print("用法: decompress [path]"); continue
                # 默认在当前工作目录进行解压
                decompress(args[0]) 
                
            elif cmd == "break":
                if not args: print("用法: break [A/B] (模拟砸坏某块物理盘)"); continue
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
                    
            else:
                print(f"[!] 未知指令: {cmd}。输入 'help' 获取命令帮助。")
                
        except Exception as e:
            print(f"[!] 发生错误: {e}")

@eel.expose
def get_kernel_info():
    from disk_core import super_block_memory
    return f"空闲盘块={super_block_memory['nfree']}, 空闲i节点={super_block_memory['ninode']}"

def start_gui():
    """启动 Web OS 桌面"""
    print("[*] 正在启动 myOS 图形化桌面引擎...")
    # 指定前端资源文件夹
    eel.init('web')
    # 弹出一个 1024x768 的窗口，并禁用浏览器默认的控制台等特性
    eel.start('index.html', size=(1024, 768), mode='chrome', port=0)
    

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
    
    # ##命令行
    # # 1. 引导开机登录
    # boot_login()
    # # 2. 验证通过，进入命令行Shell
    # start_shell()
    
    #可视化
    start_gui()