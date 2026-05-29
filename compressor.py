# compressor.py - 模拟 Linux 内核级 zlib (DEFLATE) 压缩引擎
import zlib

def rle_compress(data: bytes) -> bytes:
    """
    【工业级 DEFLATE 压缩】(对标 Linux Btrfs 内核设计)
    利用 C 语言级的 zlib 引擎，对任意文本、英文、代码进行高阶字典匹配压缩
    """
    if not data:
        return b''
    # 使用 zlib 默认的压缩级别 (level 6) 进行高比例压缩
    return zlib.compress(data, level=6)

def rle_decompress(data: bytes) -> bytes:
    """
    【工业级 DEFLATE 解压】
    """
    if not data:
        return b''
    return zlib.decompress(data)

# --- 单元测试 ---
if __name__ == "__main__":
    # 💡 修复语法报错：先写普通字符串，然后一键编码为二进制字节流！
    test_str = "操作系统课程设计：我们不仅实现了物理双写冗余，还做出了超强防护的自动回收站系统！" 
    test_data = test_str.encode('utf-8') 
    
    compressed = rle_compress(test_data)
    decompressed = rle_decompress(compressed)
    
    print(f"[*] 原始数据: '{test_str}'")
    print(f"[*] 原始大小: {len(test_data)} 字节")
    print(f"[*] 压缩大小: {len(compressed)} 字节 (节省了 {((len(test_data) - len(compressed))/len(test_data))*100:.1f}% 的空间！)")
    print(f"[*] 解压还原: '{decompressed.decode('utf-8')}'")
    
    assert test_data == decompressed, "算法校验失败！"