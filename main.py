from api import mkdir, dir_list, chdir, rmdir
from disk_core import sync_format_all, read_block, DATASTART
from kernel import format_root_dir

if __name__ == "__main__":
    sync_format_all()
    format_root_dir()
    
    # 验证
    data = read_block(DATASTART // 512)
    print(f"[*] 根目录内容读取验证: {data[:32]}")
    mkdir("/", "home")
    mkdir("/", "usr")
    dir_list()      # 列出根目录
    chdir("home")   # 切换到 home
    dir_list()      # 列出 home 目录 (应该显示 . 和 ..)
    chdir("/")
    rmdir("/", "usr")
    dir_list()
    