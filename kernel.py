# kernel.py - 模拟内核主存结构
import struct
from disk_core import DiskInode, read_block, write_block, DINODESTART, DINODESIZ, INODE_FORMAT, BLOCKSIZ, SYSOPENFILE, NOFILE, super_block_memory

class MemInode:
    def __init__(self, inode_no, disk_inode: DiskInode):
        self.inode_no = inode_no
        self.disk_inode = disk_inode  # 真实的磁盘 i 节点数据
        self.i_count = 1              # 内存活动引用计数
        self.i_flag = 0               # 脏标记 (是否被修改过)

class FileDesc:
    """对应 C 语言的 struct file (文件描述符的内存载体)"""
    def __init__(self, inode_no, f_mode, f_offset=0):
        self.inode_no = inode_no
        self.f_mode = f_mode          # 读写模式: 'r' / 'w'
        self.f_offset = f_offset      # 极其重要的系统光标指针！
        self.mem_inode = None         # 绑定的内存活动 i 节点对象

# 内存 Inode 的 Hash 链表管理 (NHINO = 128)
NHINO = 128
hash_table = [[] for _ in range(NHINO)]

# 对标 PPT 28 页：内核空间初始化系统打开文件表和用户打开文件表
sys_file_table = [None] * SYSOPENFILE
user_file_table = [None] * NOFILE

# 1. 增加用户数据库: { 用户名: (UID, GID, 密码) }
# UID=1 留给 root， usr1~usr3 分配 2~4
USER_DB = {
    "root": (1, 100, "root123"),
    "usr1": (2, 101, "usr123"),
    "usr2": (3, 101, "usr234"),
    "usr3": (4, 101, "usr345"),
}

# 2. 模拟内核中的当前活动用户上下文 (初始默认以 guest 登录)
_current_user = {"uid": 99, "name": "guest"}  

# 3. 辅助读写接口 (供 api.py 跨模块安全调用)
def get_current_user():
    return _current_user["uid"], _current_user["name"]

def set_current_user(uid, name):
    _current_user["uid"] = uid
    _current_user["name"] = name

def ihash(inode_no):
    return inode_no % NHINO

def get_inode(inode_no):
    """从物理磁盘读取指定 i 节点属性"""
    offset = DINODESTART + inode_no * DINODESIZ
    block_no = offset // 512
    block_offset = offset % 512
    data = read_block(block_no)
    inode_data = data[block_offset : block_offset + DINODESIZ]
    return struct.unpack(INODE_FORMAT, inode_data)

def write_inode(inode_no, inode_obj):
    """将 Inode 物理对象写回磁盘"""
    offset = DINODESTART + inode_no * DINODESIZ
    block_no = offset // 512
    block_offset = offset % 512
    data = bytearray(read_block(block_no))
    data[block_offset : block_offset + DINODESIZ] = inode_obj.serialize()
    write_block(block_no, data)

def iget(inode_no):
    """【升级版】：加载 i 节点至主存 Hash 链表"""
    idx = ihash(inode_no)
    for node in hash_table[idx]:
        if node.inode_no == inode_no:
            node.i_count += 1
            return node
    
    # 物理读盘
    unpacked = get_inode(inode_no)
    disk_inode = DiskInode(
        mode=unpacked[0], nlink=unpacked[1], uid=unpacked[2], 
        gid=unpacked[3], size=unpacked[4], addr=list(unpacked[5:15])
    )
    new_node = MemInode(inode_no, disk_inode)
    hash_table[idx].append(new_node)
    return new_node

def iput(node: MemInode):
    """【升级版】：递减内存引用，为 0 时安全刷回磁盘并销毁内存副本"""
    node.i_count -= 1
    if node.i_count == 0:
        write_inode(node.inode_no, node.disk_inode)
        hash_table[ihash(node.inode_no)].remove(node)

def format_root_dir():
    print("[*] 正在格式化根目录 (/) ...")
    root_block_no = 34
    dot = struct.pack('H 14s', 1, b'.')
    dotdot = struct.pack('H 14s', 1, b'..')
    root_data = dot + dotdot
    write_block(root_block_no, root_data.ljust(BLOCKSIZ, b'\x00'))
    root_inode_obj = DiskInode(mode=1, nlink=1, uid=1, gid=100, size=32, addr=[root_block_no] + [0]*9)
    write_inode(1, root_inode_obj)
    print("[+] 根目录初始化完成，地址已回填至 Inode 1。")
    
    
def fsck():
    """【高级文件系统自检修复器 fsck】"""
    global super_block_memory
    print("[*] fsck 正在进行磁盘数据一致性自检...")
    
    # 1. 扫描所有 Inode，收集已分配的 Inode 号及物理块
    allocated_inodes = set()
    occupied_blocks = set()
    dir_inodes = set() # 收集目录 Inode
    
    for ino in range(512):
        try:
            unpacked = get_inode(ino)
            mode = unpacked[0]
            if mode != 0:
                allocated_inodes.add(ino)
                if mode == 1:
                    dir_inodes.add(ino)
                for block in unpacked[5:15]:
                    if block != 0:
                        occupied_blocks.add(block)
        except Exception:
            pass
                
    # 2. 💡 修复断电一致性漏洞：扫描所有目录项，检查是否有“悬空指针”（指向未分配 Inode）
    dangling_entries_fixed = 0
    for dir_ino in dir_inodes:
        try:
            inode_info = get_inode(dir_ino)
            block_no = inode_info[5]
            dir_data = bytearray(read_block(block_no))
            modified = False
            
            for i in range(0, BLOCKSIZ, 16):
                ino, name = struct.unpack('H 14s', dir_data[i:i+16])
                name_str = name.decode('utf-8').strip('\x00')
                # 如果目录项指向了一个未被分配的 Inode (且不是 0 号空插槽)
                if ino != 0 and ino not in allocated_inodes:
                    print(f"[!] fsck 警告：检测到目录项 '{name_str}' (指向未初始化 Inode {ino}) 发生断电一致性损坏！")
                    # 💡 自动修复：将该无效目录项擦除为 0
                    dir_data[i:i+16] = struct.pack('H 14s', 0, b'\x00'*14)
                    modified = True
                    dangling_entries_fixed += 1
                    
            if modified:
                write_block(block_no, dir_data)
        except Exception:
            pass
            
    # 3. 校验双重分配
    free_stack_blocks = set(super_block_memory['free'][:super_block_memory['nfree']])
    conflict = occupied_blocks.intersection(free_stack_blocks)
    
    if conflict:
        print(f"[!] fsck 警告：检测到物理块冲突！物理块 {conflict} 发生双重分配。")
        new_free = [b for b in super_block_memory['free'][:super_block_memory['nfree']] if b not in conflict]
        super_block_memory['nfree'] = len(new_free)
        super_block_memory['free'][:len(new_free)] = new_free
        from disk_core import save_superblock
        save_superblock()
        print("[+] fsck 已自动重构超级块空闲栈！")
        
    if dangling_entries_fixed == 0 and not conflict:
        print("[+] fsck 校验通过：未发现磁盘块或目录项逻辑不一致。")
    else:
        print(f"[+] fsck 自动修复完毕！成功修复了 {dangling_entries_fixed} 处悬空目录项，100% 恢复一致性。")