# api.py - 内核调用与物理 API 桥接层
import struct
from disk_core import read_block, write_block, BLOCKSIZ, DATASTART, ialloc, balloc, SYSOPENFILE, NOFILE
from kernel import get_inode, write_inode, iget, iput, sys_file_table, user_file_table, FileDesc

current_working_dir_inode = 1  # 初始为根目录

def namei(path):
    """路径解析"""
    parts = [p for p in path.split('/') if p]
    current_inode_no = 1
    for part in parts:
        inode_info = get_inode(current_inode_no)
        first_block = inode_info[5]
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

def iname(dir_inode_no, new_name):
    inode_info = get_inode(dir_inode_no)
    block_no = inode_info[5]
    dir_data = read_block(block_no)
    free_offset = -1
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == new_name:
            raise Exception(f"操作失败：文件或目录 '{new_name}' 已存在！")
        if ino == 0 and free_offset == -1:
            free_offset = i
    if free_offset != -1:
        return free_offset
    raise Exception("目录空间已满，无法创建新项")

def mkdir(parent_path, dirname):
    parent_ino = namei(parent_path)
    offset = iname(parent_ino, dirname)
    new_ino = ialloc()
    new_block = balloc()
    
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    dir_data[offset:offset+16] = struct.pack('H 14s', new_ino, dirname.encode('utf-8'))
    write_block(parent_block, dir_data)
    
    new_dir_data = struct.pack('H 14s', new_ino, b'.') + struct.pack('H 14s', parent_ino, b'..')
    write_block(new_block, new_dir_data.ljust(BLOCKSIZ, b'\x00'))
    
    from disk_core import DiskInode
    new_inode_obj = DiskInode(mode=1, nlink=2, size=32, addr=[new_block] + [0]*9)
    write_inode(new_ino, new_inode_obj)
    print(f"[+] 目录 '{dirname}' 创建成功，Inode: {new_ino}, Block: {new_block}")

def rmdir(parent_path, dirname):
    if dirname in ['.', '..']:
        raise Exception("不能删除系统保留目录 . 或 ..")
    parent_ino = namei(parent_path)
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    
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
    target_inode_info = get_inode(target_ino)
    target_block = target_inode_info[5]
    
    from disk_core import bfree, ifree
    bfree(target_block)
    ifree(target_ino)
    
    dir_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    write_block(parent_block, dir_data)
    print(f"[-] 目录 '{dirname}' 已成功删除，释放 Inode: {target_ino}, Block: {target_block}")

def chdir(path):
    global current_working_dir_inode
    new_ino = namei(path)
    current_working_dir_inode = new_ino
    print(f"[+] 当前目录已切换至 Inode: {new_ino}")

def dir_list():
    global current_working_dir_inode
    inode_info = get_inode(current_working_dir_inode)
    block_no = inode_info[5] 
    dir_data = read_block(block_no)
    print(f"\n--- 目录内容 (Inode: {current_working_dir_inode}) ---")
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        if ino != 0:
            name_str = name.decode('utf-8').strip('\x00')
            item_info = get_inode(ino)
            type_str = "<DIR>" if item_info[0] == 1 else "<FILE>"
            size = item_info[4]
            print(f"    {type_str:<6} {name_str:<10} (Inode: {ino}, Size: {size}B)")
    print("----------------------------\n")

def create(parent_path, filename):
    parent_ino = namei(parent_path)
    offset = iname(parent_ino, filename)
    new_ino = ialloc()
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    dir_data[offset:offset+16] = struct.pack('H 14s', new_ino, filename.encode('utf-8'))
    write_block(parent_block, dir_data)
    
    from disk_core import DiskInode
    new_inode_obj = DiskInode(mode=2, nlink=1, size=0, addr=[0]*10)
    write_inode(new_ino, new_inode_obj)
    print(f"[+] 文件 '{filename}' 创建成功，Inode: {new_ino} (初始大小: 0 字节)")

# --- 🚀 核心升级：标准的 open, close, write, read ---

def open_file(filepath, mode='r'):
    """打开文件，分配文件描述符 fd"""
    ino = namei(filepath)
    inode_info = get_inode(ino)
    if inode_info[0] == 1:
        raise Exception("操作失败：不能打开一个目录")
        
    mem_inode = iget(ino) # 载入内存活动 i 节点 (引用+1)
    
    # 在【系统打开文件表】中寻找空槽位
    sys_idx = -1
    for i in range(SYSOPENFILE):
        if sys_file_table[i] is None:
            sys_idx = i
            break
    if sys_idx == -1:
        iput(mem_inode)
        raise Exception("内核分配错误：系统打开文件表已满")
        
    f_desc = FileDesc(ino, mode, f_offset=0)
    f_desc.mem_inode = mem_inode
    sys_file_table[sys_idx] = f_desc
    
    # 在【用户打开文件表】中寻找空槽位
    fd = -1
    for i in range(NOFILE):
        if user_file_table[i] is None:
            fd = i
            break
    if fd == -1:
        sys_file_table[sys_idx] = None
        iput(mem_inode)
        raise Exception("进程错误：用户文件描述符已满")
        
    user_file_table[fd] = sys_idx
    print(f"[+] 打开文件 '{filepath}' (模式: {mode})，分配描述符 fd = {fd}")
    return fd

def close_file(fd):
    """关闭文件，释放内核资源"""
    if fd < 0 or fd >= NOFILE or user_file_table[fd] is None:
        raise Exception("操作失败：无效的文件描述符")
        
    sys_idx = user_file_table[fd]
    f_desc = sys_file_table[sys_idx]
    
    # 释放内存活动 i 节点 (引用-1，如果归零则刷回磁盘)
    iput(f_desc.mem_inode)
    
    # 释放双表位置
    sys_file_table[sys_idx] = None
    user_file_table[fd] = None
    print(f"[-] 关闭描述符 fd = {fd}")

def write_file(fd, text_content):
    """基于文件描述符与光标写入文本"""
    if fd < 0 or fd >= NOFILE or user_file_table[fd] is None:
        raise Exception("操作失败：无效的文件描述符")
        
    sys_idx = user_file_table[fd]
    f_desc = sys_file_table[sys_idx]
    
    if 'w' not in f_desc.f_mode:
        raise Exception("读写许可错误：该描述符只读")
        
    mem_inode = f_desc.mem_inode
    disk_inode = mem_inode.disk_inode
    
    data_bytes = text_content.encode('utf-8')
    if f_desc.f_offset + len(data_bytes) > BLOCKSIZ:
        raise Exception("当前版本暂不支持单文件超 512 字节写入")
        
    block_no = disk_inode.addr[0]
    if block_no == 0:
        block_no = balloc()
        disk_inode.addr[0] = block_no
        
    # 物理读盘块内容 -> 在光标处修改字节 -> 同步写回物理盘
    block_data = bytearray(read_block(block_no))
    offset = f_desc.f_offset
    block_data[offset : offset + len(data_bytes)] = data_bytes
    write_block(block_no, block_data)
    
    # 光标自动向后移动
    f_desc.f_offset += len(data_bytes)
    # 文件物理大小等于光标最大游走位置
    if f_desc.f_offset > disk_inode.size:
        disk_inode.size = f_desc.f_offset
        
    print(f"[+] fd={fd} 写入了 {len(data_bytes)} 字节，光标位置 -> {f_desc.f_offset}")

def read_file(fd, size=None):
    """基于文件描述符与光标读取数据"""
    if fd < 0 or fd >= NOFILE or user_file_table[fd] is None:
        raise Exception("操作失败：无效的文件描述符")
        
    sys_idx = user_file_table[fd]
    f_desc = sys_file_table[sys_idx]
    
    mem_inode = f_desc.mem_inode
    disk_inode = mem_inode.disk_inode
    
    offset = f_desc.f_offset
    file_size = disk_inode.size
    
    if offset >= file_size:
        return "" # 已经到文件末尾了
        
    # 如果不传入大小，默认把后面所有内容全读出来
    read_size = file_size - offset if size is None else min(size, file_size - offset)
    
    block_no = disk_inode.addr[0]
    block_data = read_block(block_no)
    
    text = block_data[offset : offset + read_size].decode('utf-8')
    f_desc.f_offset += read_size # 读光标向后移动
    return text

# 软删除与还原暂不修改 (它们操作的是文件目录层，不需要动物理 Inode 属性)
def delete(parent_path, filename):
    parent_ino = namei(parent_path)
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    target_ino = 0
    target_offset = 0
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == filename:
            target_ino = ino
            target_offset = i
            break
    if target_ino == 0:
        raise Exception(f"找不到文件/目录: {filename}")
    dir_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    write_block(parent_block, dir_data)
    trash_ino = namei("/.trash")
    trash_offset = iname(trash_ino, filename)
    trash_inode_info = get_inode(trash_ino)
    trash_block = trash_inode_info[5]
    trash_data = bytearray(read_block(trash_block))
    trash_data[trash_offset:trash_offset+16] = struct.pack('H 14s', target_ino, filename.encode('utf-8'))
    write_block(trash_block, trash_data)
    print(f"[-] '{filename}' 已移入回收站 (/.trash)")

def restore(filename, target_path):
    trash_ino = namei("/.trash")
    trash_inode_info = get_inode(trash_ino)
    trash_block = trash_inode_info[5]
    trash_data = bytearray(read_block(trash_block))
    target_ino = 0
    target_offset = 0
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', trash_data[i:i+16])
        name_str = name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == filename:
            target_ino = ino
            target_offset = i
            break
    if target_ino == 0:
        raise Exception(f"回收站中找不到文件: {filename}")
    trash_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    write_block(trash_block, trash_data)
    dest_ino = namei(target_path)
    dest_offset = iname(dest_ino, filename)
    dest_inode_info = get_inode(dest_ino)
    dest_block = dest_inode_info[5]
    dest_data = bytearray(read_block(dest_block))
    dest_data[dest_offset:dest_offset+16] = struct.pack('H 14s', target_ino, filename.encode('utf-8'))
    write_block(dest_block, dest_data)
    print(f"[+] '{filename}' 已从回收站成功还原至 {target_path}")
    
# 追加到 api.py 最底部
def hard_delete(parent_path, filename):
    """彻底删除普通文件 (物理回收，不放入回收站)"""
    parent_ino = namei(parent_path)
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    
    target_ino = 0
    target_offset = 0
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == filename:
            target_ino = ino
            target_offset = i
            break
            
    if target_ino == 0:
        raise Exception(f"找不到文件: {filename}")
        
    target_inode_info = get_inode(target_ino)
    if target_inode_info[0] == 1: # mode == 1 为目录
        raise Exception("错误：不能用 delete 删除目录，请使用 rmdir")
        
    # 物理回收该文件占用的所有数据块
    from disk_core import bfree, ifree
    for block in target_inode_info[5:15]:
        if block != 0:
            bfree(block)
            
    # 回收 i 节点
    ifree(target_ino)
    
    # 清除父目录项
    dir_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    from disk_core import write_block
    write_block(parent_block, dir_data)
    print(f"[-] 文件 '{filename}' 已物理清空并彻底删除")