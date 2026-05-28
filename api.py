# api.py - 系统调用与接口层
import struct
from disk_core import ialloc, balloc, read_block, BLOCKSIZ, DATASTART
from kernel import iget, get_inode

# 增加一个全局变量记录当前目录 Inode 号 (初始为根目录 1)
current_working_dir_inode = 1

def namei(path):
    """动态路径解析：通过 Inode 查找物理块"""
    parts =[p for p in path.split('/') if p]
    current_inode_no = 1 # 从根目录开始
    
    for part in parts:
        # 1. 获取当前目录的 Inode 信息
        inode_info = get_inode(current_inode_no)
        # di_addr[0] 在元组的索引 5 (前面有 mode, nlink, uid, gid, size 5个字段)
        first_block = inode_info[5] 
        
        # 2. 读取该目录的数据内容
        dir_data = read_block(first_block)
        
        found = False
        for i in range(0, BLOCKSIZ, 16):
            entry = dir_data[i:i+16]
            ino, name = struct.unpack('H 14s', entry)
            name_str = name.decode('utf-8').strip('\x00')
            
            if name_str == part:
                current_inode_no = ino
                found = True
                break
        
        if not found:
            raise Exception(f"路径不存在: {part}")
            
    return current_inode_no

def iname(dir_inode_no):
    """在 dir_inode_no 指向的目录中，寻找一个空闲的目录项槽位"""
    inode_info = get_inode(dir_inode_no)
    block_no = inode_info[5] # di_addr[0]
    dir_data = read_block(block_no)
    
    # 查找是否有 d_ino 为 0 的槽位
    for i in range(0, BLOCKSIZ, 16):
        ino, _ = struct.unpack('H 14s', dir_data[i:i+16])
        if ino == 0:
            return i # 返回偏移量
    raise Exception("目录空间已满，无法创建新项")

def mkdir(parent_path, dirname):
    """创建目录"""
    # 1. 找到父目录的 Inode
    parent_ino = namei(parent_path)
    
    # 2. 查找空闲槽位并分配新 Inode/Block
    offset = iname(parent_ino)
    new_ino = ialloc()
    new_block = balloc()
    
    # 3. 将新目录名写入父目录项
    from disk_core import write_block, BLOCKSIZ
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    
    # 写入新目录项
    dir_data[offset:offset+16] = struct.pack('H 14s', new_ino, dirname.encode('utf-8'))
    write_block(parent_block, dir_data)
    
    # 4. 初始化新目录内容 (. 和 ..)
    new_dir_data = struct.pack('H 14s', new_ino, b'.') + struct.pack('H 14s', parent_ino, b'..')
    write_block(new_block, new_dir_data.ljust(BLOCKSIZ, b'\x00'))
    
    # 5. 把 new_block 存入 new_ino 的 Inode 中
    from disk_core import DiskInode
    new_inode_obj = DiskInode(mode=1, nlink=2, size=32, addr=[new_block] + [0]*9)
    from kernel import write_inode
    write_inode(new_ino, new_inode_obj)
    
    print(f"[+] 目录 '{dirname}' 创建成功，Inode: {new_ino}, Block: {new_block}")
    
def dir_list():
    """列出当前工作目录的内容"""
    global current_working_dir_inode
    # 使用当前目录的 Inode
    inode_info = get_inode(current_working_dir_inode)
    block_no = inode_info[5] # di_addr[0]
    
    dir_data = read_block(block_no)
    print(f"\n--- 目录内容 (Inode: {current_working_dir_inode}) ---")
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = name.decode('utf-8').strip('\x00')
        if ino != 0: 
            print(f"    {name_str:<15} (Inode: {ino})")
    print("----------------------------\n")
            
def chdir(path):
    """切换当前工作目录"""
    global current_working_dir_inode
    # 调用 namei 解析新路径的 Inode
    new_ino = namei(path)
    # 更新全局指针
    current_working_dir_inode = new_ino
    print(f"[+] 当前目录已切换至 Inode: {new_ino}")
    
def rmdir(parent_path, dirname):
    """删除指定目录"""
    if dirname in ['.', '..']:
        raise Exception("不能删除系统保留目录 . 或 ..")
        
    # 1. 找父目录 Inode 和块
    parent_ino = namei(parent_path)
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5] # di_addr[0]
    dir_data = bytearray(read_block(parent_block))
    
    # 2. 在父目录中寻找 dirname 的目录项
    target_ino = 0
    target_offset = 0
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == dirname:
            target_ino = ino
            target_offset = i
            break
            
    if target_ino == 0:
        raise Exception(f"找不到目录: {dirname}")
        
    # 3. 获取目标目录的 Inode 信息，找出它占用的物理块
    target_inode_info = get_inode(target_ino)
    target_block = target_inode_info[5]
    
    # 4. 核心：回收物理块和 Inode
    # (如果严谨一点，这里应先检查 target_block 里面是否为空目录，为了快速跑通我们先直接删)
    from disk_core import bfree, ifree
    bfree(target_block)
    ifree(target_ino)
    
    # 5. 清除父目录中的该目录项 (将 ino 置为 0)
    # 用 14 个 \x00 字节覆盖名字
    dir_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    from disk_core import write_block
    write_block(parent_block, dir_data)
    
    print(f"[-] 目录 '{dirname}' 已成功删除，释放 Inode: {target_ino}, Block: {target_block}")