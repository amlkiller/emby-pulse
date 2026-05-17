/**
 * dashboard/charts.js
 * Chart.js 图表管理 — 趋势图 + 入库统计
 * 使用 .update() 替代 destroy/recreate 提升性能
 */

let currentTrendDim = 'day';

function switchTrend(dim) {
    currentTrendDim = dim;
    ['day', 'week', 'month'].forEach(d => {
        const btn = document.getElementById(`trend-btn-${d}`);
        if (!btn) return;
        btn.className = d === dim
            ? 'px-3.5 py-1.5 rounded-md bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-white transition font-medium'
            : 'px-3.5 py-1.5 rounded-md text-gray-500 hover:text-gray-900 dark:hover:text-white transition';
    });
    initTrendChart(document.getElementById('dash-user-select').value, dim);
}

async function initTrendChart(userId, dimension = 'day') {
    const ctx = document.getElementById('trendChart').getContext('2d');
    const isDark = document.documentElement.classList.contains('dark');
    const textColor = isDark ? '#6b7280' : '#9ca3af';

    // 🔥 使用 AbortSignal，不阻塞
    fetchJSON(`/api/stats/trend?user_id=${userId}&dimension=${dimension}`, { signal: getDashboardSignal() })
        .then(json => {
            const data = json.data || {};
            const labels = Object.keys(data);
            const values = Object.values(data).map(v => Math.round(v / 3600));

            const gradient = ctx.createLinearGradient(0, 0, 0, 300);
            gradient.addColorStop(0, isDark ? 'rgba(0, 122, 255, 0.3)' : 'rgba(0, 122, 255, 0.15)');
            gradient.addColorStop(1, 'rgba(0, 122, 255, 0.0)');
            const borderColor = '#007AFF';

            const chartData = {
                labels: labels.length > 0 ? labels : ['无数据'],
                datasets: [{
                    label: '播放时长',
                    data: values.length > 0 ? values : [0],
                    borderColor, backgroundColor: gradient,
                    borderWidth: 2.5,
                    pointBackgroundColor: borderColor,
                    pointBorderColor: isDark ? '#1C1C1E' : '#fff',
                    pointBorderWidth: 2, pointRadius: 0, pointHoverRadius: 5,
                    fill: true, tension: 0.4
                }]
            };

            const chartOpts = {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: isDark ? 'rgba(28,28,30,0.9)' : 'rgba(255,255,255,0.9)',
                        titleColor: isDark ? '#F5F5F7' : '#1C1C1E',
                        bodyColor: isDark ? '#A1A1A6' : '#6E6E73',
                        borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)',
                        borderWidth: 1, padding: 10, displayColors: false,
                        titleFont: { size: 13, weight: '600' }, bodyFont: { size: 12 },
                        callbacks: { label: (ctx) => ctx.parsed.y + ' 小时' }
                    }
                },
                scales: {
                    y: { beginAtZero: true, border: { display: false }, grid: { display: false }, ticks: { display: false } },
                    x: { border: { display: false }, grid: { display: false }, ticks: { font: { family: 'ui-monospace, SFPro, sans-serif', size: 10 }, color: textColor, maxTicksLimit: 6, maxRotation: 0 } }
                }
            };

            // 复用已有实例或创建新实例
            if (window._trendChart) {
                window._trendChart.data = chartData;
                window._trendChart.options = chartOpts;
                window._trendChart.update();
            } else {
                window._trendChart = new Chart(ctx, { type: 'line', data: chartData, options: chartOpts });
            }
        })
        .catch(e => {
            if (e.name !== 'AbortError') {
                console.error('[TrendChart] 加载失败:', e);
            }
        });
}

/* ---- 入库统计柱状图（服务端缓存 + 前端缓存） ---- */
const ADDED_CACHE_KEY = 'ep_added_stats_v2';
const ADDED_CACHE_TTL = 300000; // 5分钟

async function fetchAddedStats() {
    const container = document.getElementById('addedStatsChart');
    
    // 🔥 先从 localStorage 缓存渲染（秒出）
    try {
        const cached = localStorage.getItem(ADDED_CACHE_KEY);
        if (cached) {
            const { data, ts } = JSON.parse(cached);
            if (data && Date.now() - ts < ADDED_CACHE_TTL) {
                renderAddedChart(data);
                document.getElementById('added-week-total').textContent = data.total_this_week || 0;
                console.log('[Dashboard] 入库统计从缓存渲染');
            }
        }
    } catch (e) {}
    
    // 🔥 后台请求新数据（不阻塞，使用 AbortSignal）
    fetchJSON('/api/stats/recent_added', { noCache: true, signal: getDashboardSignal() })
        .then(json => {
            if (json.status !== 'success') return;
            const d = json.data;

            // 更新数字
            document.getElementById('added-week-total').textContent = d.total_this_week || 0;
            
            // 渲染图表
            renderAddedChart(d);
            
            // 缓存到 localStorage
            localStorage.setItem(ADDED_CACHE_KEY, JSON.stringify({ data: d, ts: Date.now() }));
            
            console.log('[Dashboard] 入库统计刷新完成');
        })
        .catch(e => {
            if (e.name !== 'AbortError') {
                console.error('[Dashboard] 入库统计请求失败:', e);
            }
        });
}

function renderAddedChart(d) {
    const canvas = document.getElementById('addedStatsChart');
    if (!canvas) {
        console.error('[Dashboard] 找不到 addedStatsChart 元素');
        return;
    }

    console.log('[Dashboard] renderAddedChart 收到数据:', d);
    
    const data = d.trend || [0,0,0,0,0,0,0];
    console.log('[Dashboard] trend 数据:', data);
    
    const labels = ['一', '二', '三', '四', '五', '六', '日'];
    const isDark = document.documentElement.classList.contains('dark');
    const barColor = isDark ? '#f97316' : '#fb923c';
    const textColor = isDark ? '#9ca3af' : '#6b7280';
    const maxVal = Math.max(...data, 1);

    // 获取容器
    let container = canvas.parentElement;
    
    // 创建或获取 wrapper
    let chartWrapper = container.querySelector('.added-chart-wrapper');
    if (!chartWrapper) {
        chartWrapper = document.createElement('div');
        chartWrapper.className = 'added-chart-wrapper';
        chartWrapper.style.cssText = 'display:flex;align-items:flex-end;justify-content:space-between;height:100%;width:100%;padding:0 2px;';
        canvas.style.display = 'none';
        container.appendChild(chartWrapper);
    }

    // 清空并渲染柱状图
    chartWrapper.innerHTML = '';
    data.forEach((val, i) => {
        const col = document.createElement('div');
        col.style.cssText = 'display:flex;flex-direction:column;align-items:center;flex:1;max-width:32px;height:100%;';

        // 数值
        const num = document.createElement('span');
        num.textContent = val;
        num.style.cssText = `font-size:10px;font-weight:700;font-family:ui-monospace,monospace;color:${textColor};margin-bottom:2px;flex-shrink:0;`;

        // 柱子容器（固定高度）
        const barContainer = document.createElement('div');
        barContainer.style.cssText = 'width:100%;height:40px;position:relative;flex-shrink:0;';

        // 柱子（绝对定位，从底部向上生长）
        const bar = document.createElement('div');
        const heightPct = maxVal > 0 ? (val / maxVal) * 100 : 0;
        bar.style.cssText = `position:absolute;bottom:0;left:0;right:0;background:${barColor};border-radius:3px 3px 0 0;min-height:2px;height:${heightPct}%;transition:height 0.5s ease;`;

        // 星期标签
        const label = document.createElement('span');
        label.textContent = labels[i];
        label.style.cssText = `font-size:9px;font-weight:500;color:${textColor};margin-top:3px;opacity:0.7;flex-shrink:0;`;

        barContainer.appendChild(bar);
        col.appendChild(num);
        col.appendChild(barContainer);
        col.appendChild(label);
        chartWrapper.appendChild(col);
    });
    
    console.log('[Dashboard] 柱状图渲染完成，柱子数量:', data.length);
}

window.switchTrend = switchTrend;
window.initTrendChart = initTrendChart;
window.fetchAddedStats = fetchAddedStats;
window.currentTrendDim = currentTrendDim;
// 让外部能读到当前维度
Object.defineProperty(window, 'currentTrendDim', {
    get: () => currentTrendDim,
    set: (v) => { currentTrendDim = v; }
});
