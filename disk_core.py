import struct
import os
import sys

DATA_DIR = "data"
DISK_A = os.path.join(DATA_DIR, "disk_A.bin")
DISK_B = os.path.join(DATA_DIR, "disk_B.bin")

# --- 1. 物理常量定义 ---
BLOCKSIZ = 512
DINODESIZ = 32
NICFREE = 50
NICINOD = 50
DINODESTART = 2 * BLOCKSIZ 
DINODEBLK = 32
DATASTART = (2 + DINODEBLK) * BLOCKSIZ
SYSOPENFILE = 40  # 系统打开文件表最大长度
NOFILE = 20       # 用户打开文件表最大长度 (单个用户最多同时打开 20 个文件)

# --- 2. 结构体二进制打包格式定义 ---
# i 节点格式: H(type), h(nlink), H(uid), H(gid), I(size), 10H(addr) -> 总共 32 字节
INODE_FORMAT = 'H h H H I 10H' 
# H (unsigned short, 2字节)  h (signed short, 2字节)  I (unsigned int, 4字节) 10H (10个 unsigned short, 共20字节)

# 超级块格式 (简化版): I(isize), I(fsize), H(nfree), 50H(free), H(ninode), 50H(inode), B(flock), B(ilock), B(fmod), B(ronly), I(time)
SUPERBLOCK_FORMAT = 'I I H 50H H 50H B B B B I'

# 超级块在内存中的镜像 (全局变量，模拟内核中的超级块)
# s_isize=32, s_fsize=20480, s_nfree=0, s_free=[0]*50, s_ninode=0, s_inode=[0]*50...
super_block_memory = {
    'isize': 32, 'fsize': 20480,
    'nfree': 0, 'free': [0] * 50,
    'ninode': 0, 'inode': [0] * 50
}

# AB盘是否正常
disk_a_healthy = True
disk_b_healthy = True
# 超级块脏标记 (当内存中的超级块状态发生变化时，置为 True，表示需要写回磁盘)
superblock_dirty = False  
damaged_blocks_a = set() # 记录磁盘A的物理坏道块号
damaged_blocks_b = set() # 记录磁盘B的物理坏道块号

class DiskInode:
    def __init__(self, mode=0, nlink=0, uid=0, gid=0, size=0, addr=None):
        self.mode = mode
        self.nlink = nlink
        self.uid = uid
        self.gid = gid
        self.size = size
        self.addr = addr if addr else [0] * 10

    def serialize(self):
        return struct.pack(INODE_FORMAT, self.mode, self.nlink, self.uid, self.gid, self.size, *self.addr)


def init_virtual_disk(filename, num_blocks=20480, force=False):
    """
    初始化虚拟磁盘文件
    force=True 时，无论文件是否存在，都会执行物理清零（填入 10MB 的 0x00）
    """
    folder = os.path.dirname(filename)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)
        print(f"[*] 已自动创建缺失的目录: {folder}")
        
    if os.path.exists(filename) and not force:
        print(f"[*] 磁盘文件 {filename} 已存在，跳过物理清零。")
        return
    
    print(f"[*] 正在执行物理清零：{filename} ...")
    # 'wb' 模式打开会直接清空原有文件内容，重新写入全 0
    with open(filename, 'wb') as f:
        f.write(b'\x00' * (num_blocks * BLOCKSIZ))
    
    # 写入初始的空超级块（防止挂载报错）
    superblock_data = struct.pack(SUPERBLOCK_FORMAT, 32, num_blocks, 0, *([0]*50), 0, *([0]*50), 0, 0, 0, 0, 0)
    with open(filename, 'r+b') as f:
        f.seek(BLOCKSIZ) 
        f.write(superblock_data)

def balloc():
    """【成组链接分配器】：动态弹栈。当栈空时，物理读入组长盘块以载入下一组信息"""
    global super_block_memory, disk_a_healthy, disk_b_healthy, superblock_dirty
    
    if super_block_memory['nfree'] == 0:
        raise Exception("物理灾难：磁盘空间已完全耗尽！无空闲盘块。")
        
    # 1. 弹栈
    super_block_memory['nfree'] -= 1
    block_no = super_block_memory['free'][super_block_memory['nfree']]
    
    # 2. 💡 核心设计：如果分配的是当前栈里的最后一个块，它在物理上就是下一组的“组长块”！
    if super_block_memory['nfree'] == 0:
        print(f"[*] 栈空，正在从组长块 {block_no} 中物理加载下一组空闲块号...")
        # 物理读出该组长块里保存的下一组空闲链数据
        data = read_block(block_no)
        
        # 解包前 4 字节获取下一组的块数
        count = struct.unpack('I', data[0:4])[0]
        if count > 0:
            # 读出剩余的块号，重新填满超级块空闲栈
            blocks = struct.unpack('I' * count, data[4 : 4 + 4 * count])
            super_block_memory['nfree'] = count
            super_block_memory['free'][:count] = list(blocks)
            print(f"[+] 成功跨越组界！从组长块中加载了 {count} 个新空闲块，当前可用: {super_block_memory['nfree']}")
        else:
            # 物理空闲块真正彻底耗尽
            super_block_memory['nfree'] = 0
            
    superblock_dirty = True
    # save_superblock()
    return block_no

def bfree(block_no):
    """【成组链接回收器】：动态压栈。当栈满时，将当前栈打包写回 block_no 作新的组长块"""
    global super_block_memory, superblock_dirty
    
    # 💡 核心设计：如果内存栈已满 (50个)，必须将当前栈内容写入即将回收的块中，作为新的“组长块”！
    if super_block_memory['nfree'] == 50:
        print(f"[*] 超级块空闲栈满(50个)，正在将当前栈数据打包写回物理块 {block_no} 作新组长块...")
        count = super_block_memory['nfree']
        data = struct.pack('I', count)
        for b in super_block_memory['free'][:count]:
            data += struct.pack('I', b)
            
        # 写入物理磁盘块 [17]
        write_block(block_no, data.ljust(BLOCKSIZ, b'\x00'))
        
        # 重置超级块栈，使其只包含这一个新组长块
        super_block_memory['nfree'] = 1
        super_block_memory['free'][0] = block_no
    else:
        # 栈未满，直接压栈
        super_block_memory['free'][super_block_memory['nfree']] = block_no
        super_block_memory['nfree'] += 1
        
    superblock_dirty = True
    # save_superblock()

def format_disk(filename):
    """【标准 UNIX 成组链接格式化】：每个组长块在磁盘上存储下一组的全部块号"""
    print(f"[*] 正在为 {filename} 进行物理格式化布局...")
    
    # 物理空闲块：35 到 20479 (安全剔除保留区)
    all_blocks = list(range(35, 20480))
    
    # 将所有空闲块切分为 50 个一组
    groups = [all_blocks[i:i + 50] for i in range(0, len(all_blocks), 50)]
    
    with open(filename, 'r+b') as f:
        # 最后一组写入 0 (代表无下一组，链表终点)
        next_group_data = struct.pack('I', 0) + b'\x00' * 508
        
        # 💡 从后往前遍历：每一组的组长块写入【下一组】的块信息！
        for i in range(len(groups) - 1, -1, -1):
            current_group = groups[i]
            leader_block = current_group[0] # 组长物理块号
            
            # 将下一组的指针链数据写入当前组长块的物理扇区
            f.seek(leader_block * BLOCKSIZ)
            f.write(next_group_data)
            
            # 为前一个组长块准备数据：当前组的大小 + 当前组的所有成员块号
            count = len(current_group)
            next_group_data = struct.pack('I', count)
            for b in current_group:
                next_group_data += struct.pack('I', b)
            next_group_data = next_group_data.ljust(BLOCKSIZ, b'\x00')
            
    print(f"[+] {filename} 格式化完毕，标准成组链接链表构建完成。")
        
def ialloc():
    """分配一个空的 i 节点"""
    global super_block_memory
    
    # 检查是否有空闲的 i 节点
    if super_block_memory['ninode'] == 0:
        # 这里应该有一个从磁盘 i 节点区扫描并填充栈的逻辑
        # 简单起见，如果栈空，先手动扫描 Block 2~33 寻找空闲节点
        # ... (后续阶段完善扫描逻辑)
        raise Exception("无可用 i 节点")
    
    # 从栈顶弹出一个 i 节点号
    super_block_memory['ninode'] -= 1
    inode_no = super_block_memory['inode'][super_block_memory['ninode']]
    # save_superblock()
    global superblock_dirty
    superblock_dirty = True
    
    return inode_no

def ifree(inode_no):
    """释放一个 i 节点"""
    global super_block_memory
    
    # 将释放的 i 节点号压入栈顶 (如果栈未满)
    if super_block_memory['ninode'] < NICINOD:
        super_block_memory['inode'][super_block_memory['ninode']] = inode_no
        super_block_memory['ninode'] += 1
    else:
        # 如果栈满了，可以考虑把它存回磁盘的某个位置 (类似成组链接)
        pass
    # save_superblock()
    global superblock_dirty
    superblock_dirty = True

def init_inode_stack():
    """将前 50 个 i 节点压入超级块的空闲栈"""
    global super_block_memory
    super_block_memory['ninode'] = 50
    # 0 号留作"空指针"，1 号留给"根目录"。
    # 所以空闲栈里的 i 节点从 2 开始，一直到 51
    for i in range(50):
        super_block_memory['inode'][i] = i + 2 
    print("[+] i 节点空闲栈已初始化 (预留了 Inode 0 和 1)。")
    
    
def init_free_list():
    """【内存挂载】：将第一组空闲块直接加载入内存超级块栈中"""
    global super_block_memory
    # 第一组：35 到 84 (共 50 个空闲块)
    first_group = list(range(35, 85)) 
    super_block_memory['nfree'] = len(first_group)
    super_block_memory['free'][:len(first_group)] = first_group
    print(f"[+] 内存超级块空闲栈初始化完毕，当前可用块数: {len(first_group)}")
    

def sync_format_all():
    """同时初始化并格式化所有盘，确保 RAID-1 状态一致 (重置内存所有脏状态)"""
    global disk_a_healthy, disk_b_healthy, damaged_blocks_a, damaged_blocks_b
    import sys
    disk_a_healthy = True
    disk_b_healthy = True
    damaged_blocks_a.clear()
    if hasattr(sys.modules[__name__], 'damaged_blocks_b'):
        damaged_blocks_b.clear()
        
    disks = [DISK_A, DISK_B]
    for disk in disks:
        init_virtual_disk(disk, force=True) # 物理全盘清零 [11]
        format_disk(disk)
        
    init_free_list() 
    init_inode_stack()
    save_superblock() 
    print("[+] 所有虚拟磁盘已完成『物理级』同步格式化并清空内存状态。")
  
def write_block(block_no, data):
    """物理写盘块：支持 RAID-1 双盘智能双写与对称坏道拦截"""
    global disk_a_healthy, disk_b_healthy, damaged_blocks_a, damaged_blocks_b
    
    written_a = False
    written_b = False
    
    # 写入 A 盘
    if disk_a_healthy and (block_no not in damaged_blocks_a):
        try:
            with open(DISK_A, "r+b") as f:
                f.seek(block_no * BLOCKSIZ)
                f.write(data)
                written_a = True
        except Exception:
            disk_a_healthy = False
            
    # 写入 B 盘
    if disk_b_healthy and (block_no not in damaged_blocks_b):
        try:
            with open(DISK_B, "r+b") as f:
                f.seek(block_no * BLOCKSIZ)
                f.write(data)
                written_b = True
        except Exception:
            disk_b_healthy = False
            
    # 💡 核心防护：如果该物理盘块在 A、B 双盘上全部损坏，直接在底层抛出致命写入错误！
    if not written_a and not written_b:
        raise Exception("致命灾难：磁盘 A 与 B 的对应物理盘块均已损坏，数据写入失败！")

def read_block(block_no):
    """物理读盘块：实现无缝的热插拔/磁盘损坏自动降级切换 (带双盘对称坏道防御)"""
    global disk_a_healthy, disk_b_healthy, damaged_blocks_a, damaged_blocks_b
    
    # 1. 尝试从 A 盘读取
    if disk_a_healthy and (block_no not in damaged_blocks_a):
        try:
            with open(DISK_A, "rb") as f:
                f.seek(block_no * BLOCKSIZ)
                return f.read(BLOCKSIZ)
        except Exception:
            disk_a_healthy = False
            print("[!] 警告：物理磁盘 A 故障！系统自动无缝切换到备份磁盘 B ...")
            
    # 2. 从 B 盘读取 (A 坏了，或者 A 有坏道)
    if disk_b_healthy and (block_no not in damaged_blocks_b):
        try:
            with open(DISK_B, "rb") as f:
                f.seek(block_no * BLOCKSIZ)
                return f.read(BLOCKSIZ)
        except Exception:
            disk_b_healthy = False
            raise Exception("物理灾难：双盘全部损坏，数据丢失！")
            
    # 💡 如果 A、B 两个对应的物理盘块全部遭遇损坏，触发硬件级彻底丢失警报！
    raise Exception("物理灾难：主盘与备盘的对应盘块均已严重损坏，数据彻底丢失无法读取！")
  
def save_superblock():
    """【物理保存】：将内存中的超级块状态，持久化写入 A/B 双盘的 Block 1"""
    global super_block_memory
    # 按照 SUPERBLOCK_FORMAT 打包数据 (前 220 字节)
    data = struct.pack(
        SUPERBLOCK_FORMAT,
        super_block_memory['isize'],
        super_block_memory['fsize'],
        super_block_memory['nfree'],
        *super_block_memory['free'],
        super_block_memory['ninode'],
        *super_block_memory['inode'],
        0, 0, 0, 0, 0 # 锁及时间戳置0
    )
    # 填充至 512 字节并写入 Block 1
    write_block(1, data.ljust(BLOCKSIZ, b'\x00'))

def load_superblock():
    """【物理挂载】：开机时，从磁盘 Block 1 读取并恢复内存超级块状态"""
    global super_block_memory
    # 从磁盘 A 读取 Block 1
    data = read_block(1)
    # 解包前 220 字节
    unpacked = struct.unpack(SUPERBLOCK_FORMAT, data[:220])
    
    # 恢复内存状态
    super_block_memory['isize'] = unpacked[0]
    super_block_memory['fsize'] = unpacked[1]
    super_block_memory['nfree'] = unpacked[2]
    super_block_memory['free'] = list(unpacked[3:53])
    super_block_memory['ninode'] = unpacked[53]
    super_block_memory['inode'] = list(unpacked[54:104])
    print(f"[+] 磁盘挂载成功！已恢复超级块内存状态 (空闲盘块: {super_block_memory['nfree']}, 空闲i节点: {super_block_memory['ninode']})")


def reconstruct_disk_a_from_b():
    """【RAID-1 物理重构 - 高效流式版】：一次性流式复制，解决句柄开销瓶颈"""
    global disk_a_healthy, disk_b_healthy
    damaged_b = getattr(sys.modules[__name__], 'damaged_blocks_b', set()) if 'sys' in globals() else set()
    if not disk_b_healthy or len(damaged_b) > 0:
        raise Exception("致命灾难：备份磁盘 B 存在物理坏道或已下线，无法作为安全的镜像源进行重构恢复！系统数据已面临永久丢失风险！")
        
    print("[*] 正在进行 RAID-1 物理数据重构 (Disk B -> Disk A) ...")
    
    # 重新激活磁盘 A 的健康标志
    disk_a_healthy = True
    
    # 💡 极速优化：只打开一次文件句柄，利用底层的 read/write 流式瞬间写满 10MB！
    # "wb" 模式会自动清空磁盘 A（相当于插回了一块全新的空白盘 A）
    with open(DISK_B, "rb") as f_src, open(DISK_A, "wb") as f_dest:
        f_dest.write(f_src.read())
        
    damaged_blocks_a.clear() 
    disk_a_healthy = True
    print("[+] RAID-1 物理重构完毕！磁盘 A 状态已恢复，双盘镜像重归一致。")



# --- 3. 执行初始化 ---
if __name__ == "__main__":
    pass