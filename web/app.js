// 当页面加载完成时，立刻向 Python 内核发送问候
window.onload = async function() {
    // 调用 Python 中用 @eel.expose 暴露的 get_kernel_info 函数
    let info = await eel.get_kernel_info()();
    
    // 把 Python 返回的系统信息显示在桌面上
    document.getElementById("status-text").innerText = "内核连接成功！当前挂载信息: " + info;
}