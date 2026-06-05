// ==========================================
// 🚀 跑分测试引擎 (Benchmark Dashboard)
// ==========================================

// 窗口控制
document.getElementById("btn-benchmark").addEventListener("click", () => {
    let win = document.getElementById("win-benchmark");
    win.style.display = "flex"; win.style.top = "5%"; win.style.left = "10%";
    bringToFront(win);
});
document.getElementById("close-benchmark").addEventListener("click", () => document.getElementById("win-benchmark").style.display = "none");
makeDraggable(document.getElementById("win-benchmark"));

const benchConsole = document.getElementById("bench-console");
let myChart = null; // Chart.js 实例

// 往控制台追加日志并滚动到底部
function appendLog(text) {
    benchConsole.innerHTML += text + "\n";
    benchConsole.scrollTop = benchConsole.scrollHeight;
}

// ----------------- 执行单项测试 -----------------
async function runSingleTest(testNum) {
    appendLog(`\n[系统] 正在启动测试项目 ${testNum}... 请稍候...`);
    
    if (testNum === 1) {
        let res = await eel.run_benchmark_project_1()();
        appendLog(res);
    } 
    else if (testNum === 2) {
        let res = await eel.run_benchmark_project_2()();
        if (res.success) {
            appendLog(`=== 项目 2：动态多级冗余特征压缩率测试 ===`);
            appendLog(`[+] 测试文件总数: ${res.total_files} | 触发防膨胀 Bypass 拦截: ${res.bypass_count} 次`);
            appendLog(`[+] 全盘平均空间优化率: ${res.overall_saving_rate}%\n详细数据请查看右侧图表！`);
            renderCompressionChart(res.details); // 💡 触发图表渲染！
        } else {
            appendLog(`[!] 测试失败: ${res.error}`);
        }
    } 
    else if (testNum === 3) {
        let res = await eel.run_benchmark_project_3()();
        appendLog(res);
    } 
    else if (testNum === 4) {
        let res = await eel.run_benchmark_project_4()();
        appendLog(res);
    }
}

// ----------------- 一键完整测试 (按顺序自动执行) -----------------
document.getElementById("btn-bench-all").addEventListener("click", async function() {
    benchConsole.innerHTML = "🚀 myOS Benchmark Suite 初始化完成...\n";
    let btns = document.querySelectorAll(".window-toolbar button");
    btns.forEach(b => b.disabled = true); // 禁用按钮防止重复点击
    
    try {
        for (let i = 1; i <= 4; i++) {
            await runSingleTest(i);
        }
        appendLog("\n🎉 一键完整跑分测试全部执行完毕！你可以点击上方按钮导出报告。");
    } finally {
        btns.forEach(b => b.disabled = false);
    }
});

// 绑定 4 个独立测试按钮
document.querySelectorAll(".btn-bench-single").forEach(btn => {
    btn.addEventListener("click", async function() {
        let testNum = parseInt(this.getAttribute("data-target"));
        let btns = document.querySelectorAll(".window-toolbar button");
        btns.forEach(b => b.disabled = true);
        await runSingleTest(testNum);
        btns.forEach(b => b.disabled = false);
    });
});

// ----------------- 图表渲染引擎 (Chart.js) -----------------
function renderCompressionChart(details) {
    document.getElementById("chart-placeholder").style.display = "none";
    let canvas = document.getElementById("benchChartCanvas");
    canvas.style.display = "block";
    
    let labels = details.map(d => d.name.substring(0, 10) + "...");
    let origSizes = details.map(d => d.orig_size);
    let compSizes = details.map(d => d.comp_size);

    if (myChart) myChart.destroy(); // 销毁旧图表
    
    let ctx = canvas.getContext('2d');
    myChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: '原始大小 (Bytes)', data: origSizes, backgroundColor: '#ff79c6' },
                { label: '压缩后大小 (Bytes)', data: compSizes, backgroundColor: '#8be9fd' }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: '项目 2：文件压缩率分析柱状图', color: '#fff' },
                legend: { labels: { color: '#fff' } }
            },
            scales: {
                y: { ticks: { color: '#ccc' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                x: { ticks: { color: '#ccc' }, grid: { color: 'rgba(255,255,255,0.1)' } }
            }
        }
    });
}

// ----------------- 导出 TXT 与 导出 图表 -----------------
document.getElementById("btn-export-txt").addEventListener("click", () => {
    let content = benchConsole.innerText;
    if (!content.trim()) return alert("日志为空，请先运行测试！");
    let blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    let link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "myOS_Benchmark_Report.txt";
    link.click();
});

document.getElementById("btn-export-chart").addEventListener("click", () => {
    if (!myChart) return alert("请先运行 [2. 冗余压缩率] 生成图表！");
    let link = document.createElement("a");
    link.href = document.getElementById("benchChartCanvas").toDataURL("image/png");
    link.download = "myOS_Compression_Chart.png";
    link.click();
});