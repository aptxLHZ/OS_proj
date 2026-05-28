# main.py - 模拟操作系统的交互式 Shell
import os
import sys
from disk_core import sync_format_all
from kernel import format_root_dir
from api import (
    mkdir, rmdir, chdir, dir_list, create, delete, restore, hard_delete,
    open_file, close_file, write_file, read_file, show_disk_map, current_working_dir_inode
)

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
            from api import current_working_dir_inode
            prompt = f"usr1@myOS:[Inode {current_working_dir_inode}]$ "
            
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
                print("\n--- 📖 系统调用指令清单 ---")
                print("  ls / dir               : 列出当前工作目录内容")
                print("  cd [path]              : 切换当前目录")
                print("  mkdir [name]           : 创建子目录")
                print("  rmdir [name]           : 删除子目录")
                print("  create [name]          : 创建空文件")
                print("  open [path] [r/w]      : 打开文件并分配 fd")
                print("  write [fd] [content]   : 往 fd 写入文本")
                print("  read [fd]              : 读出 fd 中所有内容")
                print("  close [fd]             : 关闭指定描述符 fd")
                print("  delete [name]          : 软删除文件(移入回收站)")
                print("  restore [name] [path]  : 还原回收站的文件")
                print("  hard_delete [name]     : 物理彻底删除文件")
                print("  map                    : 查看前100个物理盘块占用图谱")
                print("  format                 : 重新格式化磁盘(会清空所有数据)")
                print("  exit                   : 安全退出系统\n")
                
            elif cmd in ["ls", "dir"]:
                dir_list()
                
            elif cmd == "cd":
                if not args: print("用法: cd [path]"); continue
                chdir(args[0])
                
            elif cmd == "mkdir":
                if not args: print("用法: mkdir [dirname]"); continue
                # 默认在当前目录下创建，使用相对路径机制
                mkdir("/", args[0])
                
            elif cmd == "rmdir":
                if not args: print("用法: rmdir [dirname]"); continue
                rmdir("/", args[0])
                
            elif cmd == "create":
                if not args: print("用法: create [filename]"); continue
                create("/", args[0])
                
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
                delete("/", args[0])
                
            elif cmd == "restore":
                if len(args) < 2: print("用法: restore [name] [dest_path]"); continue
                restore(args[0], args[1])
                
            elif cmd == "hard_delete":
                if not args: print("用法: hard_delete [name]"); continue
                hard_delete("/", args[0])
                
            elif cmd == "map":
                show_disk_map()
                
            elif cmd == "format":
                confirm = input("[!] 此操作会抹去 A/B 盘所有数据，确定格式化吗？(y/n): ").strip().lower()
                if confirm == 'y':
                    sync_format_all()
                    format_root_dir()
                    # 自动建立一个回收站，保证回收站功能可用
                    mkdir("/", ".trash")
                    
            else:
                print(f"[!] 未知指令: {cmd}。输入 'help' 获取命令帮助。")
                
        except Exception as e:
            print(f"[!] 发生错误: {e}")

if __name__ == "__main__":
    # 如果 data/ 目录下文件坏了或者没有，自动执行初始化
    from disk_core import DISK_A, DISK_B
    if not os.path.exists(DISK_A) or not os.path.exists(DISK_B):
        sync_format_all()
        format_root_dir()
        mkdir("/", ".trash")
    
    # 启动交互式 Shell 终端
    start_shell()