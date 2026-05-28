# kernel.py - 模拟内核内存中的数据结构
from disk_core import DiskInode, struct, read_block, write_block, DINODESTART, DINODESIZ, INODE_FORMAT, BLOCKSIZ

# 内存 i 节点 (Memory Inode) - 比磁盘 i 节点多了引用计数和标志位
class MemInode:
    def __init__(self, inode_no, disk_inode: DiskInode):
        self.inode_no = inode_no
        self.disk_inode = disk_inode # 对应的磁盘 i 节点副本
        self.i_count = 1             # 引用计数
        self.i_flag = 0              # 状态标志 (是否被修改)

# Hash 链表管理内存活动 i 节点
# 对标课件第 16 页，NHINO = 128
NHINO = 128
hash_table = [[] for _ in range(NHINO)]

def ihash(inode_no):
    return inode_no % NHINO

def iget(inode_no):
    """获取一个 i 节点，如果已在内存则返回，否则从磁盘加载"""
    idx = ihash(inode_no)
    for node in hash_table[idx]:
        if node.inode_no == inode_no:
            node.i_count += 1
            return node
    
    # 模拟从磁盘读取: 这里先伪造一个，后续任务 2.2 完善真实读盘
    print(f"[*] 加载 i 节点 {inode_no} 到内存...")
    new_node = MemInode(inode_no, DiskInode()) 
    hash_table[idx].append(new_node)
    return new_node

def iput(node: MemInode):
    """释放 i 节点引用"""
    node.i_count -= 1
    if node.i_count == 0:
        # 如果引用为0，可以从 Hash 表移除并写回磁盘
        print(f"[*] i 节点 {node.inode_no} 引用为0，准备回收...")
        # hash_table[ihash(node.inode_no)].remove(node)
        

def format_root_dir():
    print("[*] 正在格式化根目录 (/) ...")
    
    # 1. 准备数据块
    root_inode_no = 1 # 根目录的 Inode 号固定为 1 
    root_block_no = 34 # 根目录强制存放在第 34 块
    
    import struct
    dot = struct.pack('H 14s', 1, b'.')    # . 指向1号节点
    dotdot = struct.pack('H 14s', 1, b'..') # .. 指向1号节点
    root_data = dot + dotdot
    
    # 2. 写入数据块
    from disk_core import write_block, BLOCKSIZ
    write_block(root_block_no, root_data.ljust(BLOCKSIZ, b'\x00'))
    
    # 3. 【关键联动】：修改 0# Inode 并写回磁盘
    # 构造一个新的 Inode 结构: mode=DIR(1), nlink=1, size=32, addr[0]=34
    from disk_core import DiskInode, DINODESTART, DINODESIZ
    root_inode = DiskInode(mode=1, nlink=1, size=32, addr=[root_block_no] + [0]*9)
    
    # 将 Inode 序列化并写回磁盘
    inode_bytes = root_inode.serialize()
    # 找到 0# Inode 在磁盘上的绝对位置
    inode_offset = DINODESTART # 0# Inode 的位置就是 DINODESTART
    
    # 使用磁盘读写工具写回
    from disk_core import write_block
    # 这里我们只写部分：把 Inode 写入块 2 的前 32 字节
    # 注意：为了简化，这里直接覆盖块 2，后续如果 Inode 变多需要更精确的偏移读取
    inode_block_data = bytearray(512)
    inode_block_data[0:32] = inode_bytes
    write_block(2, inode_block_data) 
    
    print("[+] 根目录初始化完成，地址已回填至 Inode 0。")
    
def get_inode(inode_no):
    """从磁盘读取指定 i 节点"""
    # 计算 i 节点在磁盘上的偏移量
    offset = DINODESTART + inode_no * DINODESIZ
    block_no = offset // 512
    block_offset = offset % 512
    
    # 读块并解包
    data = read_block(block_no)
    inode_data = data[block_offset : block_offset + DINODESIZ]
    
    # 使用之前定义的 INODE_FORMAT
    from disk_core import INODE_FORMAT
    unpacked = struct.unpack(INODE_FORMAT, inode_data)
    return unpacked # 返回一个元组包含 Inode 所有信息

def write_inode(inode_no, inode_obj):
    """将 Inode 对象写回磁盘"""
    offset = DINODESTART + inode_no * DINODESIZ
    block_no = offset // 512
    block_offset = offset % 512
    
    # 读出原块，修改其中 32 字节，再写回
    data = bytearray(read_block(block_no))
    data[block_offset : block_offset + DINODESIZ] = inode_obj.serialize()
    write_block(block_no, data)