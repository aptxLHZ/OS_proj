# main.py - 模拟操作系统的交互式 Shell
import os
import sys
from disk_core import sync_format_all
from kernel import format_root_dir, get_current_user, set_current_user
from api import (
    mkdir, rmdir, chdir, dir_list, create, delete, restore, hard_delete,
    open_file, close_file, write_file, read_file, show_disk_map,
    current_working_dir_inode, login, logout, rename
)
import getpass

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
                    
            else:
                print(f"[!] 未知指令: {cmd}。输入 'help' 获取命令帮助。")
                
        except Exception as e:
            print(f"[!] 发生错误: {e}")

if __name__ == "__main__":
    # 如果 data/ 目录下文件坏了或者没有，自动执行初始化
    from disk_core import DISK_A, DISK_B, load_superblock, save_superblock
    if not os.path.exists(DISK_A) or not os.path.exists(DISK_B):
        sync_format_all()
        format_root_dir()
        mkdir("/", ".trash")
    else:
        load_superblock()
    
    # 1. 引导开机登录
    boot_login()
    # 2. 验证通过，进入命令行 Shell
    start_shell()