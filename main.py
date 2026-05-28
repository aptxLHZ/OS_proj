from api import mkdir, dir_list, chdir, rmdir, create, delete, restore, write_file, read_file, open_file, close_file, hard_delete
from disk_core import sync_format_all, read_block, DATASTART
from kernel import format_root_dir

if __name__ == "__main__":
    sync_format_all()
    format_root_dir()
    
    # 验证
    data = read_block(DATASTART // 512)
    print(f"[*] 根目录内容读取验证: {data[:32]}")
    
    # 1. 建立文件
    create("/", "diary.txt")
    
    # 2. 以可写模式打开文件，获取 fd
    fd = open_file("/diary.txt", mode="w")
    
    # 3. 连续写入两次！测试光标的自动向后累加
    write_file(fd, "今天天气真好，")
    write_file(fd, "我们成功写完了 open 和 close。")
    
    # 4. 读之前，必须关闭原写指针
    close_file(fd)
    
    print("\n[*] 写入后的目录结构状态：")
    dir_list() # 此时会显示 52 字节 (15+37)
    
    # 5. 以可读模式重新打开，验证读取
    fd_read = open_file("/diary.txt", mode="r")
    content1 = read_file(fd_read, size=15) # 只读前 15 字节
    content2 = read_file(fd_read)         # 接着光标往后读完
    
    print("\n[*] 第一次读取 (只读前15字节)：")
    print(f"-> {content1}")
    
    print("\n[*] 第二次读取 (从光标继续往后读)：")
    print(f"-> {content2}")
    
    close_file(fd_read)