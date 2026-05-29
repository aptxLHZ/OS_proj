import struct
import os

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

def init_virtual_disk(filename, num_blocks=20480):
    """初始化 10MB 的虚拟磁盘文件 (10MB / 512B = 20480 个块)"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if os.path.exists(filename):
        print(f"[*] 磁盘文件 {filename} 已存在，跳过初始化。")
        return
    
    print(f"[*] 正在初始化磁盘文件 {filename}...")
    # 创建 num_blocks * 512 字节的空文件
    with open(filename, 'wb') as f:
        f.write(b'\x00' * (num_blocks * BLOCKSIZ))
    
    # 初始化超级块数据 (简单示例，置 0)
    # 在任务 1.2 中，我们将填入成组链接法的初始数据
    superblock_data = struct.pack(SUPERBLOCK_FORMAT, 32, num_blocks, 0, *([0]*50), 0, *([0]*50), 0, 0, 0, 0, 0)
    
    with open(filename, 'r+b') as f:
        f.seek(BLOCKSIZ) # 跳过引导块，从 Block 1 开始写
        f.write(superblock_data)
    print(f"[+] {filename} 初始化完成。")

def balloc():
    """分配一个物理盘块"""
    global super_block_memory
    
    if super_block_memory['nfree'] == 0:
        raise Exception("磁盘已满")
        
    # 弹出栈顶
    super_block_memory['nfree'] -= 1
    block_no = super_block_memory['free'][super_block_memory['nfree']]
    
    # 如果弹出后栈空了，说明这是最后一个元素，它是下一组的链表块地址
    if super_block_memory['nfree'] == 0:
        # 这里模拟读取下一组信息 (实际应调用 read_block 函数)
        # print(f"正在从物理块 {block_no} 加载下一组空闲块...")
        # 实际开发中，这里要调用 read_block(block_no) 并更新 super_block_memory
        pass
    # save_superblock()
    global superblock_dirty
    superblock_dirty = True
    
    return block_no

def bfree(block_no):
    """回收一个物理盘块"""
    global super_block_memory
    
    if super_block_memory['nfree'] == 50:
        # 栈满了，将当前栈内容写入 block_no，然后重置栈
        # print(f"栈满，将当前栈存入块 {block_no}")
        super_block_memory['nfree'] = 0
        
    super_block_memory['free'][super_block_memory['nfree']] = block_no
    super_block_memory['nfree'] += 1
    # save_superblock()
    global superblock_dirty
    superblock_dirty = True

def format_disk(filename):
    """初始化磁盘：建立成组链接结构"""
    print(f"[*] 正在为 {filename} 进行格式化布局...")
    
    # 物理块范围: 34 到 20479 (前34块为保留区)
    all_blocks = list(range(34, 20480))
    
    # 逆向遍历，每50个一组，构建链表
    # 每一组的第一个块存放下一组的块号和计数
    last_block_in_group = 0 # 最开始没有下一组，设为0
    
    # 将所有块分成 50 个一组
    groups = [all_blocks[i:i + 50] for i in range(0, len(all_blocks), 50)]
    
    with open(filename, 'r+b') as f:
        for group in reversed(groups):
            # 准备该组的数据:[计数, 块号1, 块号2, ..., 块号49, 下一组指针]
            # 这里简化逻辑: 存储格式为: count(4字节) + block_nos(49*4字节) + next_group_ptr(4字节)
            count = len(group)
            
            # 打包当前组数据
            data = struct.pack('I', count)
            for b in group:
                data += struct.pack('I', b)
            data += struct.pack('I', last_block_in_group)
            
            # 如果是最后一组（物理上最靠后的组），写入磁盘
            # 注意：实际 UNIX 中每组的第一个块存下一组指针
            # 为了简化，我们把当前组的信息写入组内第一个块
            f.seek(group[0] * BLOCKSIZ)
            f.write(data.ljust(BLOCKSIZ, b'\x00'))
            
            last_block_in_group = group[0]
            
    # 最后，将第一组的信息载入超级块 (Block 1)
    # 此处省略：实际应从 last_block_in_group 读取第一组数据载入内存
    print(f"[+] {filename} 格式化完毕，成组链接链表构建完成。")
        
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
    
    
def load_free_list():
    """从磁盘读取第一组空闲块到内存超级块栈"""
    global super_block_memory
    # 我们规定第一组信息写在 34 号块（数据区第一个块）或者最后一组块
    # 按照 format_disk 的逻辑，第一组空闲块号数据在某个位置
    # 为了简单，我们强制加载包含空闲块的第一组数据块 (比如 34 号块)
    data = read_block(34) 
    # 解析: 前4字节是count，后面是块号
    import struct
    count = struct.unpack('I', data[0:4])[0]
    blocks = struct.unpack('I'*count, data[4:4+4*count])
    
    super_block_memory['nfree'] = count
    super_block_memory['free'][:count] = list(blocks)
    print(f"[+] 磁盘空闲块链表已加载到内存，当前可用块数: {count}")
    

def sync_format_all():
    """同时初始化并格式化所有盘，确保 RAID-1 状态一致"""
    disks = [DISK_A, DISK_B]
    for disk in disks:
        init_virtual_disk(disk)
        format_disk(disk)
    load_free_list()     
    # 初始化内存中的管理结构
    init_inode_stack()
    save_superblock()
    print("[+] 所有虚拟磁盘已完成 RAID-1 同步格式化。")
    
    
def write_block(block_no, data):
    """物理写盘块：支持 RAID-1 双盘智能双写"""
    global disk_a_healthy, disk_b_healthy
    # 写入 A 盘
    if disk_a_healthy:
        try:
            with open(DISK_A, "r+b") as f:
                f.seek(block_no * BLOCKSIZ)
                f.write(data)
        except Exception:
            disk_a_healthy = False
            print("[!] 警报：物理磁盘 A 突发写入异常，已被迫降级运行！")
    # 写入 B 盘
    if disk_b_healthy:
        try:
            with open(DISK_B, "r+b") as f:
                f.seek(block_no * BLOCKSIZ)
                f.write(data)
        except Exception:
            disk_b_healthy = False
            print("[!] 警报：物理磁盘 B 突发写入异常，已被迫降级运行！")

def read_block(block_no):
    """物理读盘块：实现无缝的热插拔/磁盘损坏自动降级切换"""
    global disk_a_healthy, disk_b_healthy
    # 1. 尝试从 A 盘读取
    if disk_a_healthy:
        try:
            with open(DISK_A, "rb") as f:
                f.seek(block_no * BLOCKSIZ)
                return f.read(BLOCKSIZ)
        except Exception:
            # 💡 A 盘发生物理读取异常，标记其为不健康
            disk_a_healthy = False
            print("[!] 警告：物理磁盘 A 故障！系统自动无缝切换到备份磁盘 B ...")
    # 2. 如果 A 盘坏了，或者 A 盘在前面报错了，自动从 B 盘读取数据
    if disk_b_healthy:
        try:
            with open(DISK_B, "rb") as f:
                f.seek(block_no * BLOCKSIZ)
                return f.read(BLOCKSIZ)
        except Exception:
            disk_b_healthy = False
            raise Exception("物理灾难：双盘全部损坏，数据丢失！")
    raise Exception("物理灾难：无任何可用健康的磁盘介质！")

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
    
    if not disk_b_healthy:
        raise Exception("重构失败：备份磁盘 B 也已损坏，无法进行数据同步！")
        
    print("[*] 正在进行 RAID-1 物理数据重构 (Disk B -> Disk A) ...")
    
    # 重新激活磁盘 A 的健康标志
    disk_a_healthy = True
    
    # 💡 极速优化：只打开一次文件句柄，利用底层的 read/write 流式瞬间写满 10MB！
    # "wb" 模式会自动清空磁盘 A（相当于插回了一块全新的空白盘 A）
    with open(DISK_B, "rb") as f_src, open(DISK_A, "wb") as f_dest:
        f_dest.write(f_src.read())
            
    print("[+] RAID-1 物理重构完毕！磁盘 A 状态已恢复，双盘镜像重归一致。")



# --- 3. 执行初始化 ---
if __name__ == "__main__":
    pass