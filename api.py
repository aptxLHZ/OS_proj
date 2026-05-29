# api.py - 内核调用与物理 API 桥接层
import struct
from disk_core import read_block, write_block, BLOCKSIZ, DATASTART, ialloc, balloc, SYSOPENFILE, NOFILE
from kernel import get_inode, write_inode, iget, iput, sys_file_table, user_file_table, FileDesc, USER_DB, get_current_user, set_current_user

current_working_dir_inode = 1  # 初始为根目录

def namei(path):
    """动态路径解析：支持绝对路径(/开头)和相对路径"""
    global current_working_dir_inode
    
    # 1. 自动判定起点：绝对路径从 1# 开始，相对路径从当前工作目录开始
    if path.startswith("/"):
        current_inode_no = 1
    else:
        current_inode_no = current_working_dir_inode
        
    parts = [p for p in path.split('/') if p]
    
    for part in parts:
        if part == ".":
            continue # 保持当前目录不变
            
        inode_info = get_inode(current_inode_no)
        # 校验：只有目录能进行路径向下遍历
        if inode_info[0] != 1:
            raise Exception(f"路径错误：'{part}' 不是目录，无法遍历")
            
        first_block = inode_info[5]
        dir_data = read_block(first_block)
        
        found = False
        # 利用目录里天然存在的 "." 和 ".." 目录项进行寻址跳转！
        for i in range(0, BLOCKSIZ, 16):
            entry = dir_data[i:i+16]
            ino, name = struct.unpack('H 14s', entry)
            name_str = name.decode('utf-8').strip('\x00')
            if ino != 0 and name_str == part:
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
    from kernel import write_inode, get_current_user
    current_uid, _ = get_current_user()
    new_inode_obj = DiskInode(
        mode=1, nlink=2, uid=current_uid, gid=100, size=32, addr=[new_block] + [0]*9
    )
    write_inode(new_ino, new_inode_obj)
    print(f"[+] 目录 '{dirname}' 创建成功，Inode: {new_ino}, Block: {new_block}")

def chdir(path):
    global current_working_dir_inode
    new_ino = namei(path)
    current_working_dir_inode = new_ino
    print(f"[+] 当前目录已切换至 Inode: {new_ino}")
    
def _soft_delete(parent_path, name, expected_mode):
    """
    通用软删除底层逻辑 (包含类型强校验与回收站边界拦截)
    expected_mode: 1 代表目录, 2 代表文件
    """
    global current_working_dir_inode
    trash_ino = namei("/.trash")
    
    # 拦截规则：若当前处于回收站内部，严禁重复移入回收站！
    if current_working_dir_inode == trash_ino:
        raise Exception(f"操作拒绝：'{name}' 已在回收站中！若要物理彻底删除，请使用 'hard_delete' 命令。")
        
    parent_ino = namei(parent_path)
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    
    # 1. 寻找目标项的 Inode 和偏移
    target_ino = 0
    target_offset = 0
    for i in range(0, BLOCKSIZ, 16):
        ino, file_name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = file_name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == name:
            target_ino = ino
            target_offset = i
            break
            
    if target_ino == 0:
        raise Exception(f"找不到目标项: {name}")
    
    # 安全特权校验：普通目录下，只有文件属主本身或管理员 root，才有权将文件/目录移入回收站！
    current_uid, _ = get_current_user()
    target_inode_info = get_inode(target_ino)
    file_owner_uid = target_inode_info[2] # 文件的属主 UID
    if current_uid != 1 and current_uid != file_owner_uid:
        raise Exception(f"权限拒绝：您不是该文件的创建者，无权删除属于用户 {file_owner_uid} 的文件/目录 '{name}'！")
        
    # 2. 核心校验：强制隔离文件(2)与目录(1)的操作权限！
    mode = target_inode_info[0]
    if mode != expected_mode:
        if expected_mode == 2:
            raise Exception(f"操作错误：'{name}' 是一个目录文件夹，删除请使用 'rmdir' 命令！")
        else:
            raise Exception(f"操作错误：'{name}' 是一个普通文件，删除请使用 'delete' 命令！")
            
    # 3. 从原父目录中擦除该项
    dir_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    from disk_core import write_block
    write_block(parent_block, dir_data)
    
    # 4. 移入回收站目录 (/.trash)
    trash_offset = iname(trash_ino, name)
    trash_inode_info = get_inode(trash_ino)
    trash_block = trash_inode_info[5]
    trash_data = bytearray(read_block(trash_block))
    trash_data[trash_offset:trash_offset+16] = struct.pack('H 14s', target_ino, name.encode('utf-8'))
    write_block(trash_block, trash_data)
    
    # 5. 记录元数据映射 (写入 /.trashinfo 隐藏文件)
    resolved_parent_path = parent_path if parent_path != "." else "/"
    if not resolved_parent_path.startswith("/"):
         resolved_parent_path = "/" + resolved_parent_path
    try:
        try:
            namei("/.trashinfo")
        except Exception:
            create("/", ".trashinfo")
            
        fd = open_file("/.trashinfo", "w")
        old_metadata = read_file(fd)
        new_record = f"{name}:{resolved_parent_path}\n"
        write_file(fd, old_metadata + new_record)
        close_file(fd)
    except Exception as e:
        print(f"[!] 回收站元数据记录失败: {e}")
        
    type_desc = "目录" if expected_mode == 1 else "文件"
    print(f"[-] {type_desc} '{name}' 已移入回收站 (/.trash)")

def rmdir(parent_path, dirname):
    """【软删除目录文件夹】"""
    _soft_delete(parent_path, dirname, expected_mode=1)

def dir_list(detail=False):
    """列出当前工作目录的内容 (完美排版对齐版)"""
    global current_working_dir_inode
    inode_info = get_inode(current_working_dir_inode)
    block_no = inode_info[5] 
    dir_data = read_block(block_no)
    
    print(f"\n--- 目录内容 (Inode: {current_working_dir_inode}) ---")
    
    # 💡 使用标准的 UNIX 风格表头，彻底避免中西文字符宽度错位！
    if detail:
        print(f"    {'PERMISSIONS':<12} {'OWNER':<8} {'SIZE':<8} {'BLOCK':<6} {'NAME'}")
        print(f"    {'-'*55}")
        
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        if ino != 0:
            name_str = name.decode('utf-8').strip('\x00')
            item_info = get_inode(ino)
            mode = item_info[0]
            size = item_info[4]
            
            if detail:
                perm_str = "d" if mode == 1 else "-"
                perm_str += "rwxr-xr-x" if mode == 1 else "rw-r--r--"
                
                # 完善的属主用户名映射逻辑，彻底消灭 usr-1 和 usr98 
                owner_uid = item_info[2]
                if owner_uid == 1:
                    owner_name = "root"
                elif owner_uid == 99:
                    owner_name = "guest"
                elif 2 <= owner_uid <= 10:
                    owner_name = f"usr{owner_uid-1}"
                else:
                    owner_name = f"uid:{owner_uid}"
                
                phys_block = item_info[5]
                # 精准间距控制
                print(f"    {perm_str:<12} {owner_name:<8} {size:<5}B   Block:{phys_block:<3} {name_str:<12} (Inode: {ino})")
            else:
                type_str = "<DIR>" if mode == 1 else "<FILE>"
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
    from kernel import write_inode, get_current_user
    current_uid, _ = get_current_user()
    new_inode_obj = DiskInode(
        mode=2, nlink=1, uid=current_uid, gid=100, size=0, addr=[0]*10
    )
    write_inode(new_ino, new_inode_obj)
    print(f"[+] 文件 '{filename}' 创建成功，Inode: {new_ino} (初始大小: 0 字节)")

def delete(parent_path, filename):
    """【软删除普通文件】"""
    _soft_delete(parent_path, filename, expected_mode=2)


def open_file(filepath, mode='r'):
    """打开文件，分配文件描述符 fd"""
    ino = namei(filepath)
    inode_info = get_inode(ino)
    # 保护锁：禁止直接读写回收站内的任何文件！
    trash_ino = namei("/.trash")
    if (current_working_dir_inode == trash_ino or "/.trash/" in filepath) and ".trashinfo" not in filepath:
        raise Exception("权限拒绝：回收站内的文件已被系统安全锁定，禁止直接打开或修改！")
    
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
    """基于文件描述符与光标读取数据 (💡 支持对压缩文件进行全自动、透明解压读取！)"""
    if fd < 0 or fd >= NOFILE or user_file_table[fd] is None:
        raise Exception("操作失败：无效的文件描述符")
        
    sys_idx = user_file_table[fd]
    f_desc = sys_file_table[sys_idx]
    
    mem_inode = f_desc.mem_inode
    disk_inode = mem_inode.disk_inode
    
    offset = f_desc.f_offset
    
    # 💡 保护锁：如果文件的 mode == 3，说明是压缩状态，自动在内核内存中进行透明解压！
    is_compressed = (disk_inode.mode == 3)
    block_no = disk_inode.addr[0]
    block_data = read_block(block_no)
    
    if is_compressed:
        compressed_size = disk_inode.size
        # 自动调用解压引擎还原真实数据
        actual_data = rle_decompress(block_data[:compressed_size])
        file_size = len(actual_data)
    else:
        actual_data = block_data
        file_size = disk_inode.size
        
    if offset >= file_size:
        return "" # 读到末尾
        
    read_size = file_size - offset if size is None else min(size, file_size - offset)
    
    text = actual_data[offset : offset + read_size].decode('utf-8')
    f_desc.f_offset += read_size # 移动读写指针
    return text

def restore(filename):
    """【升级为全自动还原】：从 /.trashinfo 读取原始路径，实现无缝自动归位！"""
    # 1. 打开元数据配置文件，解析出原始路径
    try:
        fd_info = open_file("/.trashinfo", "r")
        metadata = read_file(fd_info)
        close_file(fd_info)
    except Exception:
        raise Exception("回收站中没有任何文件的还原备份记录！")
        
    lines = metadata.strip().split('\n')
    target_path = None
    remaining_lines = []
    
    for line in lines:
        if not line:
            continue
        parts = line.split(":")
        if parts[0] == filename:
            target_path = parts[1] # 找到了原路径！
        else:
            remaining_lines.append(line) # 保留其他文件的记录
            
    if target_path is None:
        raise Exception(f"回收站元数据中找不到该项的还原记录: {filename}")
        
    # 2. 从回收站 (/.trash) 目录中擦除该项
    trash_ino = namei("/.trash")
    trash_inode_info = get_inode(trash_ino)
    trash_block = trash_inode_info[5]
    trash_data = bytearray(read_block(trash_block))
    
    target_ino = 0
    target_offset = 0
    for i in range(0, BLOCKSIZ, 16):
        ino, file_name = struct.unpack('H 14s', trash_data[i:i+16])
        name_str = file_name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == filename:
            target_ino = ino
            target_offset = i
            break
            
    if target_ino == 0:
        raise Exception(f"回收站中找不到文件: {filename}")
        
    trash_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    write_block(trash_block, trash_data)
    
    # 3. 将其无缝写入原始目标路径！
    # 属主越权校验：非创建者本人且非管理员 root，无权还原该文件！
    current_uid, _ = get_current_user()
    target_inode_info = get_inode(target_ino)
    file_owner_uid = target_inode_info[2] # Inode 元组中 di_uid 索引为 2
    if current_uid != 1 and current_uid != file_owner_uid:
        raise Exception("权限拒绝：您不是该文件的创建者，无权还原其他用户扔进回收站的文件！")
    dest_ino = namei(target_path)
    dest_offset = iname(dest_ino, filename)
    dest_inode_info = get_inode(dest_ino)
    dest_block = dest_inode_info[5]
    dest_data = bytearray(read_block(dest_block))
    
    dest_data[dest_offset:dest_offset+16] = struct.pack('H 14s', target_ino, filename.encode('utf-8'))
    write_block(dest_block, dest_data)
    
    # 4. 更新 /.trashinfo 文件，剔除已经还原的记录
    fd_info = open_file("/.trashinfo", "w")
    new_metadata = "\n".join(remaining_lines) + ("\n" if remaining_lines else "")
    write_file(fd_info, new_metadata)
    close_file(fd_info)
    
    print(f"[+] '{filename}' 已【自动还原】至其原始目录: {target_path}")

def hard_delete(parent_path, name):
    """【彻底物理删除】：回收所有的物理块和 Inode 号 (全面支持普通文件和目录)"""
    if name in ['.', '..', '.trash', '.trashinfo']:
        raise Exception("系统保护项，禁止物理彻底删除！")
        
    parent_ino = namei(parent_path)
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    
    # 1. 寻找目标项的 Inode
    target_ino = 0
    target_offset = 0
    for i in range(0, BLOCKSIZ, 16):
        ino, file_name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = file_name.decode('utf-8').strip('\x00')
        if ino != 0 and name_str == name:
            target_ino = ino
            target_offset = i
            break
            
    if target_ino == 0:
        raise Exception(f"找不到项: {name}")
        
    target_inode_info = get_inode(target_ino)
    mode = target_inode_info[0]
    
    # 2. 回收物理块
    from disk_core import bfree, ifree
    if mode == 1: # 目录
        # 回收目录占用的那个数据块
        target_block = target_inode_info[5]
        bfree(target_block)
    elif mode == 2: # 文件
        # 遍历回收普通文件占用的所有数据块
        for block in target_inode_info[5:15]:
            if block != 0:
                bfree(block)
                
    # 3. 回收 i 节点
    ifree(target_ino)
    
    # 4. 从父目录中擦除项
    # 属主越权校验：如果是在回收站内进行彻底物理删除，必须进行属主校验
    trash_ino = namei("/.trash")
    if parent_ino == trash_ino:
        current_uid, _ = get_current_user()
        file_owner_uid = target_inode_info[2]
        if current_uid != 1 and current_uid != file_owner_uid:
            raise Exception("权限拒绝：您不是该文件的创建者，无权在回收站中彻底物理删除此文件！")
    dir_data[target_offset:target_offset+16] = struct.pack('H 14s', 0, b'\x00'*14)
    from disk_core import write_block
    write_block(parent_block, dir_data)
    
    # 5. 【元数据同步】：若该文件是从回收站 (/.trash) 彻底物理删除的，自动清除 /.trashinfo 里的历史恢复路径
    trash_ino = namei("/.trash")
    if parent_ino == trash_ino:
        try:
            fd_info = open_file("/.trashinfo", "r")
            metadata = read_file(fd_info)
            close_file(fd_info)
            
            lines = metadata.strip().split('\n')
            # 过滤掉关于这个被彻底删除的文件的历史记录
            remaining_lines = [line for line in lines if line and not line.startswith(f"{name}:")]
            
            fd_info = open_file("/.trashinfo", "w")
            new_metadata = "\n".join(remaining_lines) + ("\n" if remaining_lines else "")
            write_file(fd_info, new_metadata)
            close_file(fd_info)
        except Exception:
            pass
            
    type_desc = "目录" if mode == 1 else "文件"
    print(f"[-] {type_desc} '{name}' 已物理清空并彻底删除")
   
def show_disk_map(start_block=0, count=100):
    """磁盘物理块可视化监控：支持自定义起始块和查看数量"""
    total_blocks = 20480
    if start_block < 0 or start_block >= total_blocks:
        raise Exception(f"起始块号错误。有效范围: 0 ~ {total_blocks-1}")
        
    end_block = min(start_block + count, total_blocks)
    display_count = end_block - start_block
    
    # 初始化局部显示矩阵
    disk_map = ["."] * display_count
    
    # 1. 标记物理保留区 (只有当显示范围覆盖了这些区域时才标记)
    for i in range(display_count):
        phys_no = start_block + i
        if phys_no == 0:
            disk_map[i] = "B"
        elif phys_no == 1:
            disk_map[i] = "S"
        elif 2 <= phys_no <= 33:
            disk_map[i] = "I"
            
    # 2. 扫描所有 512 个 i 节点找占用的数据块
    for ino in range(512):
        try:
            inode_info = get_inode(ino)
            mode = inode_info[0]
            if mode != 0: # 被占用
                for block in inode_info[5:15]:
                    if block != 0 and start_block <= block < end_block:
                        disk_map[block - start_block] = "D"
        except Exception:
            pass
            
    # 3. 打印图谱
    print(f"\n==================== 磁盘物理盘块状态图谱 (Blocks {start_block} ~ {end_block - 1}) ==================")
    print(" 标志说明: [B]:引导区 | [S]:超级块 | [I]:i节点区 | [D]:数据已占用 | [.]:空闲")
    print("------------------------------------------------------------------")
    
    # 动态分行打印 (每行 20 个块)
    blocks_per_line = 20
    lines = (display_count + blocks_per_line - 1) // blocks_per_line
    for r in range(lines):
        line_start_idx = r * blocks_per_line
        line_end_idx = min((r + 1) * blocks_per_line, display_count)
        row = disk_map[line_start_idx:line_end_idx]
        
        # 计算当前行的实际物理块号范围
        phys_start = start_block + line_start_idx
        phys_end = start_block + line_end_idx - 1
        
        row_str = " ".join([f"[{char}]" if char != "." else " . " for char in row])
        print(f"Blocks {phys_start:04d}~{phys_end:04d}:  {row_str}")
    print("==================================================================\n")
    
def login(username, password):
    """用户登录接口"""
    global current_working_dir_inode
    if username not in USER_DB:
        raise Exception(f"登录失败：用户 '{username}' 不存在！")
        
    uid, gid, pwd = USER_DB[username]
    if pwd != password:
        raise Exception("登录失败：密码错误！")
        
    # 1. 更新内核当前活动用户上下文
    set_current_user(uid, username)
    # 2. 登录成功后，安全强制将工作目录重置为根目录 (1#)
    current_working_dir_inode = 1
    print(f"[+] 用户 '{username}' (UID: {uid}) 登录成功！当前目录已重置为根目录 (/)。")

def logout():
    """用户注销接口"""
    uid, username = get_current_user()
    if username == "guest":
        print("[*] 提示：当前未登录任何账户。")
        return
        
    # 注销后，重置为未登录的 guest 状态
    set_current_user(99, "guest")
    global current_working_dir_inode
    current_working_dir_inode = 1
    print(f"[-] 用户 '{username}' 已成功注销会话。")
    
def rename(parent_path, old_name, new_name):
    """【重命名接口】：仅修改父目录项中的 14 字节名字，Inode 属性无任何变动"""
    if new_name in ['.', '..']:
        raise Exception("系统保护项，禁止修改为此名字！")
    if len(new_name.encode('utf-8')) > 14:
        raise Exception("操作失败：重命名的名字长度不能超过 14 字节！")
        
    parent_ino = namei(parent_path)
    parent_inode_info = get_inode(parent_ino)
    parent_block = parent_inode_info[5]
    dir_data = bytearray(read_block(parent_block))
    
    target_offset = -1
    target_ino = 0
    # 遍历目录：1. 确保新名字没被占用（防重名冲突）；2. 找到要改名的旧文件
    for i in range(0, BLOCKSIZ, 16):
        ino, name = struct.unpack('H 14s', dir_data[i:i+16])
        name_str = name.decode('utf-8').strip('\x00')
        
        if ino != 0 and name_str == new_name:
            raise Exception(f"操作失败：命名冲突，该目录下已存在 '{new_name}'！")
        if ino != 0 and name_str == old_name:
            target_ino = ino
            target_offset = i
            
    if target_ino == 0:
        raise Exception(f"重命名失败：当前目录下找不到文件/目录: {old_name}")
        
    # 💡 安全特权校验：只有文件属主本身或管理员 root，才有权对文件/目录进行重命名！
    current_uid, _ = get_current_user()
    target_inode_info = get_inode(target_ino)
    file_owner_uid = target_inode_info[2]
    if current_uid != 1 and current_uid != file_owner_uid:
        raise Exception(f"权限拒绝：您不是该文件的创建者，无权重命名属于用户 {file_owner_uid} 的文件/目录 '{old_name}'！")
    
    # 物理覆写：直接修改名字，保持 Inode 号(target_ino)不变
    dir_data[target_offset:target_offset+16] = struct.pack('H 14s', target_ino, new_name.encode('utf-8'))
    from disk_core import write_block
    write_block(parent_block, dir_data)
    print(f"[+] 成功将 '{old_name}' 重命名为 '{new_name}'")
    
from compressor import rle_compress, rle_decompress # 导入我们的 zlib 工业级压缩引擎

def compress(filepath):
    """【系统调用】：手动压缩文件，若压缩后变大则自动安全放弃"""
    ino = namei(filepath)
    inode_info = get_inode(ino)
    
    # 1. 状态校验
    if inode_info[0] == 1:
        raise Exception("操作失败：目录无法被压缩")
    if inode_info[0] == 3:
        raise Exception("操作失败：该文件已经是压缩状态，无需重复压缩")
        
    size = inode_info[4]
    if size == 0:
        raise Exception("操作失败：空文件无法被压缩")
        
    # 2. 读取原始数据
    block_no = inode_info[5] # di_addr[0]
    original_data = read_block(block_no)[:size] # 根据文件真实大小截取有效数据
    
    # 3. 尝试进行工业级压缩
    compressed_data = rle_compress(original_data)
    
    # 💡 安全阀门检测（防膨胀保护）：如果压缩后反而变大或没变，直接安全放弃！
    if len(compressed_data) >= len(original_data):
        print(f"[!] 提示：文件 '{filepath}' (原大小:{size}B) 缺乏重复特征，压缩后({len(compressed_data)}B)无空间优化，系统已自动取消本次压缩。")
        return
        
    # 4. 【写入物理磁盘】：将压缩后的二进制写回物理块
    from disk_core import write_block
    write_block(block_no, compressed_data.ljust(BLOCKSIZ, b'\x00'))
    
    # 5. 【修改元数据】：修改大小为【压缩后的大小】，并将 mode 置为 3 (压缩状态)
    from disk_core import DiskInode
    from kernel import write_inode
    compressed_inode = DiskInode(
        mode=3, nlink=inode_info[1], uid=inode_info[2], gid=inode_info[3], 
        size=len(compressed_data), addr=[block_no] + list(inode_info[6:15])
    )
    write_inode(ino, compressed_inode)
    
    saved_bytes = size - len(compressed_data)
    print(f"[+] '{filepath}' 压缩成功！原大小: {size}B -> 压缩后: {len(compressed_data)}B，直接节省了 {saved_bytes} 字节物理磁盘空间！")

def decompress(filepath):
    """【系统调用】：解压已被压缩的文件"""
    ino = namei(filepath)
    inode_info = get_inode(ino)
    
    if inode_info[0] != 3:
        raise Exception("操作失败：该文件当前处于未压缩状态，无法执行解压")
        
    size = inode_info[4] # 当前记录的压缩后的大小
    block_no = inode_info[5]
    compressed_data = read_block(block_no)[:size]
    
    # 1. 调用引擎解码还原
    decompressed_data = rle_decompress(compressed_data)
    
    # 2. 物理写入原大小数据
    from disk_core import write_block
    write_block(block_no, decompressed_data.ljust(BLOCKSIZ, b'\x00'))
    
    # 3. 还原 Inode：mode 变回 2 (普通文件)，size 变回原始大小
    from disk_core import DiskInode
    from kernel import write_inode
    original_inode = DiskInode(
        mode=2, nlink=inode_info[1], uid=inode_info[2], gid=inode_info[3], 
        size=len(decompressed_data), addr=[block_no] + list(inode_info[6:15])
    )
    write_inode(ino, original_inode)
    
    print(f"[+] '{filepath}' 已成功解压还原！恢复大小: {len(decompressed_data)}B。")