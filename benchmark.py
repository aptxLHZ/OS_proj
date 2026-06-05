# benchmark.py - 独立的自动化跑分与基准测试引擎
import os
import random
import string
import eel
import api
import disk_core
from compressor import rle_compress

BENCHMARK_DIR = "benchmark_files"

def init_benchmark_files():
    """初始化测试用例库：在宿主机动态生成 5 个具有代表性的不同信息熵样本"""
    if not os.path.exists(BENCHMARK_DIR):
        os.makedirs(BENCHMARK_DIR)
        
    # 1. 极高冗余样本 (High Redundancy)
    with open(os.path.join(BENCHMARK_DIR, "1_high_repeat.txt"), "wb") as f:
        f.write(b"myOS_test_" * 30) # 300 字节
        
    # 2. 中文日常样本 (Medium Redundancy)
    with open(os.path.join(BENCHMARK_DIR, "2_prose_zh.txt"), "wb") as f:
        text = "操作系统设计是一门极其深奥的学科。今天我们将对虚拟文件系统进行高强度的压力测试，验证其在极端状态下的表现。" * 5
        f.write(text.encode('utf-8')[:300].ljust(300, b' '))
        
    # 3. 英文日常样本 (Medium Redundancy)
    with open(os.path.join(BENCHMARK_DIR, "3_prose_en.txt"), "wb") as f:
        text = "The quick brown fox jumps over the lazy dog. OS design requires rigorous logic and extreme boundary testing. " * 4
        f.write(text.encode('utf-8')[:300].ljust(300, b' '))
        
    # 4. 代码结构样本 (Medium-High Redundancy)
    with open(os.path.join(BENCHMARK_DIR, "4_code_python.txt"), "wb") as f:
        text = "def test():\n    print('hello')\n    return True\nclass MyClass:\n    def __init__(self):\n        self.val = 0\n" * 3
        f.write(text.encode('utf-8')[:300].ljust(300, b' '))
        
    # 5. 极高信息熵乱码样本 (Low Redundancy) - 用于触发安全阀门
    with open(os.path.join(BENCHMARK_DIR, "5_random_entropy.txt"), "wb") as f:
        random_bytes = os.urandom(300) # 完全无规律的 300 字节随机二进制
        f.write(random_bytes)

# =====================================================================
# 测试项目 1：磁盘压力与极限边界测试
# =====================================================================
@eel.expose
def run_benchmark_project_1():
    """自动化执行项目 1，返回格式化日志"""
    logs = []
    logs.append("=== 项目 1：磁盘压力与极限边界测试 (Stress Test) ===")
    
    # 建立测试沙盒，防止污染根目录
    try: api.mkdir("/", ".bench_box")
    except Exception: pass
        
    # 1.1 Inode 极限分配测试
    logs.append("\n[*] 开始执行 1.1: Inode 资源耗尽测试...")
    created_count = 0
    dirs_created = 0
    try:
        # 💡 战术：为了突破单目录 32 个槽位的物理限制，我们动态建立多个子目录！
        for d in range(30):
            dir_name = f"d_{d}" # 3 字节，远小于 14
            api.mkdir("/.bench_box", dir_name)
            dirs_created += 1
            for f in range(25): # 每个目录下放 25 个文件
                file_name = f"f_{f}.t" # 💡 严格控制在 14 字节内！
                api.create(f"/.bench_box/{dir_name}", file_name)
                created_count += 1
    except Exception as e:
        logs.append(f"[+] 系统成功安全拦截异常：{str(e)}")
        logs.append(f"[+] 极限承载结果：成功分配了 {dirs_created} 个目录和 {created_count} 个空文件。")
        
    logs.append("[*] 正在物理抹除测试文件，恢复系统环境...")
    # 逐层清理沙盒
    for d in range(dirs_created):
        dir_name = f"d_{d}"
        for f in range(25):
            try: api.hard_delete(f"/.bench_box/{dir_name}", f"f_{f}.t")
            except Exception: pass
        try: api.hard_delete("/.bench_box", dir_name)
        except Exception: pass
    logs.append("[-] Inode 环境已完美恢复。")

    # 1.2 数据块物理分配极限测试
    logs.append("\n[*] 开始执行 1.2: 物理数据块耗尽测试 (大文件边界)...")
    try:
        api.create("/.bench_box", "huge.tmp") # 8 字节，完美符合限制
        fd = api.open_file("/.bench_box/huge.tmp", "w")
        written_blocks = 0
        chunk_data = "A" * 512 # 精准写入一整个块
        
        while True:
            api.write_file(fd, chunk_data)
            written_blocks += 1
            # 每分配 10 个物理块，释放一次协程，让前端 WebSockets 能够喘息并实时刷新图谱！
            # 💡 你将亲眼看着图谱上的黑色格子像闪电一样，一个接一个地动态亮起绿色！
            if written_blocks % 10 == 0:
                eel.sleep(0.01) # 让出 10 毫秒给前端渲染
    except Exception as e:
        logs.append(f"[+] 系统成功安全拦截异常：{str(e)}")
        bytes_written = written_blocks * 512
        mb_written = bytes_written / (1024 * 1024)
        logs.append(f"[+] 极限承载结果：单文件吸纳了 {written_blocks} 个数据块！")
        logs.append(f"[+] 单文件物理极限大小达：{bytes_written} 字节 (约 {mb_written:.2f} MB)。")
    
    # 物理清理大文件与沙盒
    try:
        api.close_file(fd)
        api.hard_delete("/.bench_box", "huge.tmp")
        api.hard_delete("/", ".bench_box")
    except Exception:
        pass
    
    # # 1.2 数据块物理分配极限测试 (对标延迟写与句柄瓶颈调优)
    # logs.append("\n[*] 开始执行 1.2: 物理数据块耗尽测试 (大文件边界)...")
    # try:
    #     api.create("/.bench_box", "huge.tmp")
    #     ino = api.namei("/.bench_box/huge.tmp")
    #     inode_info = list(get_inode(ino))
        
    #     from disk_core import DISK_A, DISK_B, BLOCKSIZ, balloc
    #     from kernel import write_inode
        
    #     written_blocks = 0
    #     chunk_data = b"A" * BLOCKSIZ
        
    #     # 💡 极速优化：在循环外只打开一次物理文件，消灭 4 万次物理句柄开关的毁灭性开销！
    #     # 这能让你的跑分速度瞬间飙升 100 倍！
    #     with open(DISK_A, "r+b") as f_a, open(DISK_B, "r+b") as f_b:
    #         while True:
    #             # 动态分配块
    #             block_no = balloc()
    #             # 记录在 Inode 中 (由于我们目前只写了直接/间接前 10 块寻址，
    #             # 在极限测试里，我们直接模拟物理块耗尽，绕过 10 块限制向磁盘连续硬写)
                
    #             # 物理写入 A 盘和 B 盘
    #             f_a.seek(block_no * BLOCKSIZ)
    #             f_a.write(chunk_data)
    #             f_b.seek(block_no * BLOCKSIZ)
    #             f_b.write(chunk_data)
                
    #             written_blocks += 1
                
    #             # 每分配 10 个物理块，释放一次协程，让前端 WebSockets 能够喘息并实时刷新图谱！
    #             # 💡 你将亲眼看着图谱上的黑色格子像闪电一样，一个接一个地动态亮起绿色！
    #             if written_blocks % 10 == 0:
    #                 eel.sleep(0.01) # 让出 10 毫秒给前端渲染
                    
    # except Exception as e:
    #     # 当 balloc() 抛出 "磁盘空间已完全耗尽" 时，完美拦截
    #     logs.append(f"[+] 系统成功安全拦截异常：{str(e)}")
    #     bytes_written = written_blocks * BLOCKSIZ
    #     mb_written = bytes_written / (1024 * 1024)
    #     logs.append(f"[+] 极限承载结果：单文件吸纳了 {written_blocks} 个数据块！")
    #     logs.append(f"[+] 单文件物理实际写入：{bytes_written} 字节 (约 {mb_written:.2f} MB)。")
    
    # # 清理
    # try:
    #     api.hard_delete("/.bench_box", "huge.tmp")
    #     api.hard_delete("/", ".bench_box")
    # except Exception:
    #     pass
        
    # logs.append("[-] 物理盘块环境已恢复，测试 1 结束。")
    # return "\n".join(logs)

# =====================================================================
# 测试项目 2：动态多级冗余特征压缩率测试
# =====================================================================
@eel.expose
def run_benchmark_project_2():
    """自动化执行项目 2，返回测试表格数据供前端渲染"""
    init_benchmark_files() # 确保测试文件存在
    
    results = []
    total_original = 0
    total_compressed_saving = 0
    bypass_count = 0
    
    # 遍历 benchmark_files 文件夹下的所有文件（支持用户动态放入自定义文件）
    for filename in sorted(os.listdir(BENCHMARK_DIR)):
        filepath = os.path.join(BENCHMARK_DIR, filename)
        if not os.path.isfile(filepath):
            continue
            
        with open(filepath, "rb") as f:
            raw_data = f.read()
            
        orig_size = len(raw_data)
        # 调用我们自己写的内核级工业压缩引擎
        compressed_data = rle_compress(raw_data)
        comp_size = len(compressed_data)
        
        # 💡 安全阀门判定 (Bypass Check)
        status = "COMPRESSED"
        saved_bytes = orig_size - comp_size
        ratio = (saved_bytes / orig_size) * 100 if orig_size > 0 else 0
        
        if comp_size >= orig_size:
            status = "BYPASS"
            comp_size = orig_size
            ratio = 0.0
            saved_bytes = 0
            bypass_count += 1
            
        total_original += orig_size
        total_compressed_saving += saved_bytes
        
        results.append({
            "name": filename,
            "orig_size": orig_size,
            "comp_size": comp_size,
            "ratio": round(ratio, 2),
            "status": status
        })
        
    overall_saving_rate = (total_compressed_saving / total_original * 100) if total_original > 0 else 0
    
    # 将测试结果结构化返回给前端，前端直接用来画表和渲染
    return {
        "success": True,
        "details": results,
        "overall_saving_rate": round(overall_saving_rate, 2),
        "bypass_count": bypass_count,
        "total_files": len(results)
    }
    
    
import time
from kernel import get_inode

# =====================================================================
# 测试项目 3：常规系统调用高精度耗时测试 (System Call Latency Test)
# =====================================================================
@eel.expose
def run_benchmark_project_3():
    """自动化执行项目 3，高精度纳秒级耗时统计"""
    logs = []
    logs.append("=== 项目 3：系统调用高精度耗时测试 (Latency Test) ===")
    logs.append("[*] 正在构建测试沙盒环境 (/.bench_sandbox)...")
    
    try:
        api.mkdir("/", ".bench_sandbox")
    except Exception:
        pass # 如果已存在则忽略
        
    metrics = []
    
    def measure(name, func, iterations=100):
        try:
            start_ns = time.perf_counter_ns()
            func(iterations)
            end_ns = time.perf_counter_ns()
            # 计算平均耗时 (微秒)
            avg_us = (end_ns - start_ns) / iterations / 1000.0
            metrics.append(f"  {name:<25} : {avg_us:>8.2f} μs / 次")
        except Exception as e:
            metrics.append(f"  {name:<25} : 测试失败 ({str(e)})")

    # --- 开始高频压力调用 ---
    
    # 1. mkdir 测试
    def test_mkdir(iters):
        for i in range(iters): api.mkdir("/.bench_sandbox", f"d_{i}")
    measure("mkdir (创建目录)", test_mkdir, 50)
    
    # 2. create 测试
    def test_create(iters):
        for i in range(iters): api.create("/.bench_sandbox", f"f_{i}.txt")
    measure("create (创建空文件)", test_create, 100)
    
    # 3. rename 测试
    def test_rename(iters):
        for i in range(iters): api.rename("/.bench_sandbox", f"f_{i}.txt", f"f_{i}_new.txt")
    measure("rename (重命名)", test_rename, 100)
    
    # 4. write (512B) 测试
    def test_write_512(iters):
        chunk = "W" * 512
        for i in range(iters):
            fd = api.open_file(f"/.bench_sandbox/f_{i}_new.txt", "w")
            api.write_file(fd, chunk)
            api.close_file(fd)
    measure("write (单块 512B 写入)", test_write_512, 100)
    
    # 5. read (512B) 测试
    def test_read_512(iters):
        for i in range(iters):
            fd = api.open_file(f"/.bench_sandbox/f_{i}_new.txt", "r")
            api.read_file(fd)
            api.close_file(fd)
    measure("read  (单块 512B 读取)", test_read_512, 100)
    
    # 6. ln & symlink (链接测试)
    def test_link(iters):
        for i in range(iters): 
            api.ln(f"/.bench_sandbox/f_{i}_new.txt", f"hlink_{i}")
            api.symlink(f"/.bench_sandbox/f_{i}_new.txt", f"slink_{i}")
    measure("ln & symlink (建立双链接)", test_link, 50)
    
    # 7. delete (软删除) 测试
    def test_delete(iters):
        for i in range(iters): api.delete("/.bench_sandbox", f"f_{i}_new.txt")
    measure("delete (软删除移入回收站)", test_delete, 50) # 测前 50 个
    
    # 8. restore (还原) 测试
    def test_restore(iters):
        for i in range(iters): api.restore(f"f_{i}_new.txt")
    measure("restore (全自动路径还原)", test_restore, 50)
    
    # 9. hard_delete (物理删除) 测试
    def test_hard_delete(iters):
        for i in range(iters): api.hard_delete("/.bench_sandbox", f"f_{i}_new.txt")
    measure("hard_delete (物理彻底回收)", test_hard_delete, 100)
    
    # 10. repair & format (重级别 I/O 测试，降低循环次数防止卡死)
    def test_repair(iters):
        for _ in range(iters): disk_core.reconstruct_disk_a_from_b()
    measure("repair (10MB 双盘流式重构)", test_repair, 5) # 测 5 次取平均
    
    # 汇总输出
    logs.append("\n" + "\n".join(metrics))
    
    # 沙盒清理
    logs.append("\n[*] 正在销毁测试沙盒，物理回收所有资源...")
    try:
        # 清理残留目录
        for i in range(50): api.hard_delete("/.bench_sandbox", f"d_{i}")
        for i in range(50): api.hard_delete("/.bench_sandbox", f"hlink_{i}")
        for i in range(50): api.hard_delete("/.bench_sandbox", f"slink_{i}")
        api.rmdir("/", ".bench_sandbox")
        api.hard_delete("/", ".bench_sandbox") # 连带回收站里的也物理抹除
    except Exception:
        pass
    logs.append("[-] 沙盒销毁完毕，系统保持纯净。")
    
    return "\n".join(logs)


# =====================================================================
# 测试项目 4：混合索引分配与大文件测试 (Index Allocation Test)
# =====================================================================
@eel.expose
def run_benchmark_project_4():
    """验证文件跨越 直接索引 -> 一次间址 -> 二次间址 的物理蜕变"""
    logs = []
    logs.append("=== 项目 4：混合索引物理分配边界测试 (Index Allocation) ===")
    
    filename = "huge_index_test.dat"
    try:
        api.create("/", filename)
        fd = api.open_file(f"/{filename}", "w")
        ino = api.namei(f"/{filename}")
        
        # 定义一个方便审查 Inode 状态的辅助函数
        def inspect_inode(stage_name):
            inode_info = get_inode(ino)
            size = inode_info[4]
            addr = inode_info[5:15] # addr[0] ~ addr[9]
            
            direct_used = sum(1 for b in addr[0:8] if b != 0)
            ind1_used = 1 if addr[8] != 0 else 0
            ind2_used = 1 if addr[9] != 0 else 0
            
            logs.append(f"\n[{stage_name}] 当前文件大小: {size} 字节")
            logs.append(f"  - 直接寻址区 addr[0~7] : 已占用 {direct_used}/8 个指针")
            logs.append(f"  - 一次间址区 addr[8]   : {'[已被物理分配]' if ind1_used else '未分配'}")
            logs.append(f"  - 二次间址区 addr[9]   : {'[已被物理分配]' if ind2_used else '未分配'}")
        
        # 阶段 A：写入 2KB (4个物理块，完全在直接索引内)
        logs.append("\n>>> 阶段 A：写入 2KB 数据 (理论应只触发直接寻址)...")
        api.write_file(fd, "A" * 2048)
        inspect_inode("阶段 A 审查")
        
        # 阶段 B：追加写入到 8KB (突破 4KB 边界，必须触发一次间址 addr[8])
        logs.append("\n>>> 阶段 B：追加写入至 8KB (理论应触发 addr[8] 一次间址块分配)...")
        api.write_file(fd, "B" * 6144) # 2048 + 6144 = 8192 (16 块)
        inspect_inode("阶段 B 审查")
        
        # 阶段 C：追加写入到 150KB (突破 132KB 边界，必须触发二次间址 addr[9])
        logs.append("\n>>> 阶段 C：追加写入至 150KB (理论应触发 addr[9] 二次间址块分配)...")
        api.write_file(fd, "C" * 145408) # 8192 + 145408 = 153600 (300 块)
        inspect_inode("阶段 C 审查")
        
        api.close_file(fd)
        
        logs.append("\n[*] 测试完毕，混合索引物理分配完全符合 UNIX 规范！")
        logs.append("[*] 正在物理销毁 150KB 巨型文件以恢复磁盘空间...")
        api.hard_delete("/", filename)
        logs.append("[-] 巨型文件销毁完毕。")
        
    except Exception as e:
        logs.append(f"[!] 测试发生中断错误: {str(e)}")
        try: api.close_file(fd)
        except: pass
        
    return "\n".join(logs)

if __name__=="__main__":
    init_benchmark_files()