/**
 * dashboard/init.js
 * 仪表盘入口 — 初始化布局、加载所有 widget 数据
 * 🔥 优化版：使用聚合 API 一次性获取首屏数据 + 后端预热缓存支持
 * 依赖: state.js, utils.js, layout.js, widgets.js, charts.js
 */

/* ---- 🔥 全局请求控制器 - 在文件开头立即初始化 ---- */
window._dashboardAbortController = null;
window._systemMonitorIntervalId = null;

function cancelDashboardRequests() {
    if (window._dashboardAbortController) {
        window._dashboardAbortController.abort();
        window._dashboardAbortController = null;
    }
    if (window._systemMonitorIntervalId) {
        clearInterval(window._systemMonitorIntervalId);
        window._systemMonitorIntervalId = null;
    }
}

// 页面卸载时取消请求
window.addEventListener('beforeunload', cancelDashboardRequests);

// 🔥 点击导航链接时立即取消请求 + 强制跳转
document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href]');
    if (link && link.href && !link.href.includes('#') && !link.target) {
        const href = link.href;
        if (href !== window.location.href && !href.startsWith('javascript:')) {
            cancelDashboardRequests();
            try { window.stop(); } catch (_) {}
            e.preventDefault();
            e.stopPropagation();
            window.location.href = href;
        }
    }
}, true);

/* ---- 🔥 后端预热状态检测 ---- */
let _backendPreloaded = false;

async function checkBackendPreloadStatus() {
    try {
        const json = await fetchJSON('/api/dashboard/preload_status', { noCache: true, timeout: 3000 });
        if (json.status === 'success' && json.data.cached) {
            _backendPreloaded = true;
            console.log('[Dashboard] 后端缓存已预热，cache_age:', json.data.cache_age, '秒');
            return true;
        }
        return false;
    } catch (e) {
        console.log('[Dashboard] 预热状态检测失败，使用前端缓存');
        return false;
    }
}

/* ---- 用户下拉框 ---- */
let isUserDropdownOpen = false;

async function loadUsers() {
    try {
        const json = await fetchJSON('/api/users');
        if (json.status !== 'success') return;
        const select = document.getElementById('dash-user-select');
        json.data.forEach(user => {
            const option = document.createElement('option');
            option.value = user.UserId;
            option.textContent = user.UserName;
            select.appendChild(option);
        });
        buildUserDropdown();
    } catch (_) {}
}

function buildUserDropdown() {
    const select = document.getElementById('dash-user-select');
    const list = document.getElementById('user-dropdown-list');
    list.innerHTML = '';
    Array.from(select.options).forEach(opt => {
        const isActive = opt.value === select.value;
        const cls = isActive ? 'bg-brand-500/10 text-brand-500 font-bold' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100/80 dark:hover:bg-white/5';
        const check = isActive ? '<i class="fa-solid fa-check text-[11px] text-brand-500 shrink-0 ml-2"></i>' : '';
        list.innerHTML += `<button onclick="selectUser('${escapeHtml(opt.value)}', this)" class="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-[13px] font-medium transition-colors ${cls}"><span class="truncate">${escapeHtml(opt.textContent)}</span>${check}</button>`;
    });
}

function toggleUserDropdown() {
    const panel = document.getElementById('user-dropdown-panel');
    if (isUserDropdownOpen) { closeUserDropdown(); }
    else {
        buildUserDropdown();
        panel.classList.remove('hidden');
        void panel.offsetWidth;
        panel.classList.remove('opacity-0', 'scale-95');
        panel.classList.add('opacity-100', 'scale-100');
        isUserDropdownOpen = true;
    }
}

function closeUserDropdown() {
    const panel = document.getElementById('user-dropdown-panel');
    panel.classList.remove('opacity-100', 'scale-100');
    panel.classList.add('opacity-0', 'scale-95');
    setTimeout(() => panel.classList.add('hidden'), 200);
    isUserDropdownOpen = false;
}

function selectUser(val) {
    const select = document.getElementById('dash-user-select');
    select.value = val;
    document.getElementById('dash-user-label').textContent = select.options[select.selectedIndex].textContent;
    closeUserDropdown();
    changeUser();
}

function changeUser() {
    const userId = document.getElementById('dash-user-select').value;
    localStorage.removeItem('ep_dashboard_data_cache_' + userId);
    localStorage.removeItem('ep_recent_play_cache_' + userId);
    fetchDashboardData(userId);
    fetchRecentActivity(userId);
    initTrendChart(userId, window.currentTrendDim || 'day');
}

document.addEventListener('click', (e) => {
    if (isUserDropdownOpen && !e.target.closest('#dash-user-btn') && !e.target.closest('#user-dropdown-panel')) closeUserDropdown();
});

/* ---- 看板管理 Modal ---- */
function openDashManager() {
    const modal = document.getElementById('dash-manager-modal');
    const content = document.getElementById('dash-manager-content');
    const list = document.getElementById('widget-toggle-list');
    const state = DashboardState.get();
    const names = DashboardState.widgetNames;

    list.innerHTML = '';
    state.order.forEach(id => {
        const isChecked = state.visible[id] !== false;
        list.innerHTML += `<div class="p-3.5 rounded-xl border border-gray-100 dark:border-white/5 hover:bg-gray-50 dark:hover:bg-white/5 transition-colors">
            <div class="flex items-center justify-between">
                <span class="text-[14px] font-bold text-gray-800 dark:text-gray-200">${escapeHtml(names[id] || id)}</span>
                <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" class="sr-only peer" ${isChecked ? 'checked' : ''} onchange="toggleWidgetVisibility('${id}', this.checked)">
                    <div class="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all dark:border-gray-600 peer-checked:bg-brand-500 shadow-inner"></div>
                </label>
            </div>
            <p class="text-[11px] text-gray-400 mt-1.5">点击卡片右上角 <i class="fa-solid fa-ellipsis text-[9px]"></i> 菜单调节宽度</p>
        </div>`;
    });

    modal.classList.remove('hidden'); modal.classList.add('flex');
    setTimeout(() => { modal.classList.remove('opacity-0'); content.classList.remove('scale-95'); }, 10);
}

function closeDashManager() {
    const modal = document.getElementById('dash-manager-modal');
    const content = document.getElementById('dash-manager-content');
    modal.classList.add('opacity-0'); content.classList.add('scale-95');
    setTimeout(() => { modal.classList.add('hidden'); modal.classList.remove('flex'); }, 300);
}

function toggleWidgetVisibility(id, isVisible) {
    const el = document.querySelector(`.widget-item[data-id="${id}"]`);
    if (isVisible) {
        el.classList.remove('hidden');
        el.style.animation = 'pulse 0.5s cubic-bezier(0.4, 0, 0.6, 1)';
    } else {
        el.classList.add('hidden');
    }
    DashboardState.setVisible(id, isVisible);
}

function resetDashboardLayout() {
    DashboardState.reset();
    location.reload();
}

/* ---- 骨架屏渲染 ---- */
function showSkeletons() {
    // 天气骨架
    const weatherTemp = document.getElementById('weather-temp');
    const weatherDesc = document.getElementById('weather-desc');
    if (weatherTemp) weatherTemp.innerHTML = '<span class="skeleton skeleton-text skeleton-text-xl inline-block" style="width:80px"></span>';
    if (weatherDesc) weatherDesc.innerHTML = '<span class="skeleton skeleton-text inline-block" style="width:120px"></span>';

    // 🔥 服务器状态不显示骨架屏，保持 --% 状态，等待 fetchSystemMonitor 更新
    // 因为 fetchSystemMonitor 会先从缓存读取，再后台刷新

    // 入库统计骨架
    const addedTotal = document.getElementById('added-week-total');
    if (addedTotal) addedTotal.innerHTML = '<span class="skeleton skeleton-text skeleton-text-lg inline-block" style="width:50px"></span>';

    // 媒体库储量骨架
    ['lib-movies', 'lib-series', 'lib-episodes'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<span class="skeleton skeleton-text skeleton-text-lg inline-block" style="width:40px"></span>';
    });

    // 核心指标骨架
    ['stat-plays', 'stat-users', 'stat-duration'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = '<span class="skeleton skeleton-text skeleton-text-lg inline-block" style="width:50px"></span>';
    });

    // 媒体库列表骨架
    const libContainer = document.getElementById('library-container');
    if (libContainer) {
        let libSkeleton = '<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 w-full">';
        for (let i = 0; i < 6; i++) {
            libSkeleton += `<div class="skeleton aspect-video rounded-2xl"></div>`;
        }
        libSkeleton += '</div>';
        libContainer.innerHTML = libSkeleton;
    }

    // 白金观影榜骨架
    const topContainer = document.getElementById('top-users-container');
    if (topContainer) {
        let topSkeleton = '';
        for (let i = 0; i < 5; i++) {
            topSkeleton += `<div class="skeleton-row"><div class="skeleton skeleton-avatar"></div><div class="flex-1"><div class="skeleton skeleton-text" style="width:60%"></div><div class="skeleton skeleton-text-sm mt-1" style="width:40%"></div></div></div>`;
        }
        topContainer.innerHTML = topSkeleton;
    }
}

/* ---- 🔥 主初始化（缓存优先 + 后台刷新） ---- */

/* ---- 🔥 缓存管理 ---- */
const CACHE_KEYS = {
    dashboard: 'ep_dashboard_init_cache',
    addedStats: 'ep_added_stats_cache'
};
const CACHE_TTL = 60000; // 1分钟缓存

// 从缓存立即渲染（不检查 TTL，只检查是否存在）
function renderFromCache() {
    try {
        const cached = localStorage.getItem(CACHE_KEYS.dashboard);
        if (cached) {
            const { data } = JSON.parse(cached);
            if (data) {
                // 立即渲染缓存数据
                if (data.dashboard) {
                    const lib = data.dashboard.library || {};
                    document.getElementById('lib-movies').textContent = lib.movie || '0';
                    document.getElementById('lib-series').textContent = lib.series || '0';
                    document.getElementById('lib-episodes').textContent = lib.episode || '0';
                    document.getElementById('stat-plays').textContent = data.dashboard.total_plays || '0';
                    document.getElementById('stat-users').textContent = data.dashboard.active_users || '0';
                    document.getElementById('stat-duration').textContent = Math.round((data.dashboard.total_duration || 0) / 3600) || '0';
                }
                if (data.libraries && data.libraries.length > 0) {
                    renderLibraries(data.libraries);
                }
                if (data.trend) {
                    initTrendChartWithData(data.trend);
                }
                if (data.top_users && data.top_users.length > 0) {
                    renderTopUsersList(data.top_users);
                }
                console.log('[Dashboard] 已从缓存渲染首屏');
                return true;
            }
        }
    } catch (e) {
        console.warn('[Dashboard] 缓存解析失败:', e);
    }
    return false;
}

// 渲染媒体库列表
function renderLibraries(libraries) {
    const container = document.getElementById('library-container');
    if (!container || !libraries.length) return;
    let html = '';
    libraries.forEach(lib => {
        const imageTag = lib.ImageTag || '';
        const versionParam = imageTag ? `?v=${imageTag}` : '';
        const imgUrl = `/api/proxy/image/${encodeURIComponent(lib.Id)}/primary${versionParam}`;
        const name = escapeHtml(lib.Name);
        html += `<div onclick="jumpToLibrary('${escapeHtml(lib.Id)}')" class="lib-card relative aspect-video rounded-2xl overflow-hidden cursor-pointer bg-gray-200 dark:bg-apple-hoverDark">
            <img src="${imgUrl}" class="w-full h-full object-cover transition-all duration-500 opacity-0 hover:opacity-100 hover:scale-105" onload="this.style.opacity='0.9'" onerror="this.src='/static/img/logo-app.png';this.style.opacity='0.9'" loading="lazy">
            <div class="absolute bottom-0 inset-x-0 p-3 pb-3 flex justify-center items-end bg-gradient-to-t from-black/60 to-transparent"><h4 class="text-white font-semibold text-sm md:text-[15px] truncate w-full text-center tracking-widest drop-shadow-md">${name}</h4></div>
        </div>`;
    });
    container.innerHTML = html;
    requestAnimationFrame(() => fitGridContent('library-container'));
}

// 比较数据是否有变化
function hasDataChanged(oldData, newData, keys) {
    if (!oldData || !newData) return true;
    for (const key of keys) {
        if (JSON.stringify(oldData[key]) !== JSON.stringify(newData[key])) {
            return true;
        }
    }
    return false;
}

async function init() {
    // 🔥 日期显示（立即显示，不等待）
    document.getElementById('current-date').textContent = new Date().toLocaleDateString('zh-CN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

    // 🔥 布局引擎异步初始化（不阻塞其他操作）
    Layout.init().then(() => Layout.setupResizeObserver()).catch(() => {});

    // 创建请求控制器
    window._dashboardAbortController = new AbortController();
    const signal = window._dashboardAbortController.signal;

    // 🔥 先尝试从缓存渲染（不阻塞）
    const hasCache = renderFromCache();

    // 🔥 后端预热状态检测（不阻塞，异步进行）
    checkBackendPreloadStatus().then(backendReady => {
        if (!hasCache && !backendReady) {
            showSkeletons();
            console.log('[Dashboard] 无缓存，显示骨架屏等待数据...');
        } else if (backendReady) {
            console.log('[Dashboard] 后端已预热，数据秒出！');
        }
    });

    // 获取旧缓存用于比较
    let oldCacheData = null;
    try {
        const oldCache = localStorage.getItem(CACHE_KEYS.dashboard);
        if (oldCache) {
            oldCacheData = JSON.parse(oldCache).data;
        }
    } catch (e) {}

    // ===== 🔥 后台刷新数据（每次都请求） =====
    fetchJSON('/api/dashboard/init', { signal, noCache: true }).then(initRes => {
        if (signal.aborted) return;
        if (initRes.status === 'success') {
            const data = initRes.data;

            // 更新缓存
            localStorage.setItem(CACHE_KEYS.dashboard, JSON.stringify({ data, ts: Date.now() }));

            // 🔥 检查核心数据是否有变化，有变化才更新 UI
            const coreChanged = hasDataChanged(oldCacheData, data, ['dashboard', 'libraries', 'top_users', 'trend']);
            
            if (coreChanged || !hasCache) {
                // 更新核心数据
                if (data.dashboard) {
                    const lib = data.dashboard.library || {};
                    document.getElementById('lib-movies').textContent = lib.movie || '0';
                    document.getElementById('lib-series').textContent = lib.series || '0';
                    document.getElementById('lib-episodes').textContent = lib.episode || '0';
                    document.getElementById('stat-plays').textContent = data.dashboard.total_plays || '0';
                    document.getElementById('stat-users').textContent = data.dashboard.active_users || '0';
                    document.getElementById('stat-duration').textContent = Math.round((data.dashboard.total_duration || 0) / 3600) || '0';
                }

                if (data.libraries && data.libraries.length > 0) {
                    renderLibraries(data.libraries);
                }

                if (data.top_users && data.top_users.length > 0) {
                    renderTopUsersList(data.top_users);
                }

                if (data.trend) {
                    initTrendChartWithData(data.trend);
                }
            }

            // 用户列表总是更新（可能切换用户）
            if (data.users && data.users.length > 0) {
                const select = document.getElementById('dash-user-select');
                select.innerHTML = '<option value="all">全站统计 (All Users)</option>';
                data.users.forEach(user => {
                    const option = document.createElement('option');
                    option.value = user.UserId;
                    option.textContent = user.UserName;
                    select.appendChild(option);
                });
                buildUserDropdown();
            }

            console.log('[Dashboard] 数据刷新完成', initRes.cached ? '(服务器缓存)' : '');
        }
    }).catch(e => {
        if (e.name === 'AbortError') {
            console.log('[Dashboard] 请求已取消（页面跳转）');
        } else {
            console.error('[Dashboard] 刷新失败:', e);
        }
    });

    // ===== 🔥 P1：次要数据并行加载（非阻塞） =====
    // 🔥 fetchSystemMonitor 单独执行，避免阻塞 Promise.all（系统监控 API 可能较慢）
    fetchSystemMonitor().catch(() => {});
    
    Promise.all([
        fetchWeather(),
        fetchTodayCalendar(),
        fetchConnectivity(),
        fetchTasksHealth(),
        // 🔥 入库统计单独加载（耗时操作）
        fetchAddedStats()
    ]).catch(() => {});

    // 🔥 系统监控定时刷新
    window._systemMonitorIntervalId = setInterval(fetchSystemMonitor, 5000);

    // ===== 🔥 P2：延迟加载海报列表（懒加载） =====
    setTimeout(() => {
        if (signal.aborted) return;
        lazyLoadWidget('widget-latest', fetchLatest);
        lazyLoadWidget('widget-recent-play', () => fetchRecentActivity('all'));
        lazyLoadWidget('widget-quality', fetchQualityChart);
        lazyLoadWidget('widget-clients', fetchClientsChart);
    }, 100);
}

/* ---- 渲染白金观影榜 ---- */
function renderTopUsersList(data) {
    const container = document.getElementById('top-users-container');
    if (!container) return;
    // 🔥 修复：确保 data 是数组，否则降级到独立 API
    if (!Array.isArray(data) || data.length === 0) {
        console.log('[TopUsers] 聚合 API 数据为空，降级到独立 API');
        fetchTopUsers('all');
        return;
    }
    let html = '';
    data.forEach((user, index) => {
        const rankClass = index === 0 ? 'bg-brand-500 text-white' : index === 1 ? 'bg-gray-800 text-white dark:bg-gray-300 dark:text-black' : index === 2 ? 'bg-gray-400 text-white dark:bg-gray-600 dark:text-white' : 'bg-gray-100 text-gray-500 dark:bg-apple-hoverDark dark:text-gray-400';
        const userName = escapeHtml(user.UserName);
        const initial = escapeHtml(user.UserName.charAt(0).toUpperCase());
        html += `<div onclick="jumpToUserInsight('${escapeHtml(user.UserId)}')" class="user-rank-card flex items-center justify-between p-2.5 rounded-xl">
            <div class="flex items-center min-w-0">
                <div class="w-6 h-6 rounded-md ${rankClass} flex items-center justify-center font-bold text-[11px] mr-3 shrink-0 shadow-sm">${index + 1}</div>
                <div class="relative w-9 h-9 rounded-full overflow-hidden bg-gray-100 dark:bg-apple-hoverDark shrink-0 mr-3 shadow-sm ring-1 ring-black/5 dark:ring-white/10 flex items-center justify-center">
                    <span class="font-bold text-gray-500 dark:text-gray-300 text-xs absolute z-0">${initial}</span>
                    <img src="/api/proxy/user_image/${encodeURIComponent(user.UserId)}" onload="this.style.opacity='1'" onerror="this.style.opacity='0'" class="absolute inset-0 w-full h-full object-cover opacity-0 transition-opacity duration-300 z-10">
                </div>
                <div class="truncate"><p class="text-[14px] font-medium text-gray-900 dark:text-white truncate">${userName}</p><p class="text-[11px] text-gray-500 mt-0.5">${user.Plays} 次播放</p></div>
            </div>
            <div class="flex items-center pl-3"><p class="text-[14px] font-semibold text-gray-900 dark:text-white tracking-tight text-right w-12">${Math.round(user.TotalTime/3600)}<span class="text-[9px] font-normal opacity-60 ml-0.5">h</span></p><i class="fa-solid fa-chevron-right text-[10px] text-gray-300 dark:text-gray-600 user-rank-arrow ml-2"></i></div>
        </div>`;
    });
    container.innerHTML = html;
}

/* ---- 趋势图数据初始化 ---- */
function initTrendChartWithData(data) {
    // 直接使用数据渲染趋势图
    const ctx = document.getElementById('trendChart');
    if (!ctx) return;

    const isDark = document.documentElement.classList.contains('dark');
    const textColor = isDark ? '#6b7280' : '#9ca3af';

    const labels = Object.keys(data);
    const values = Object.values(data).map(v => Math.round(v / 3600));

    const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 300);
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
    } else if (typeof Chart !== 'undefined') {
        window._trendChart = new Chart(ctx.getContext('2d'), { type: 'line', data: chartData, options: chartOpts });
    }
}

// 主题切换时重绘图表
window.addEventListener('theme-changed', () => {
    initTrendChart(document.getElementById('dash-user-select').value, window.currentTrendDim || 'day');
    fetchAddedStats();
});

/* ---- 卡片菜单（宽度调节/隐藏） ---- */
let currentMenuWidgetId = null;

function toggleWidgetMenu(event, widgetId) {
    event.stopPropagation();
    const popup = document.getElementById('widget-menu-popup');
    const isVisible = !popup.classList.contains('hidden') && currentMenuWidgetId === widgetId;

    if (isVisible) {
        hideWidgetMenu();
        return;
    }

    currentMenuWidgetId = widgetId;
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();

    // 更新宽度按钮高亮
    const state = DashboardState.get();
    const { w } = Layout.parseSizeStr(state.sizes[widgetId] || document.querySelector(`[data-id="${widgetId}"]`)?.dataset.defaultSize || '1x3');
    popup.querySelectorAll('#widget-menu-width-btns .w-btn').forEach(btnEl => {
        const btnW = parseInt(btnEl.dataset.w);
        const active = btnW === w;
        btnEl.className = 'w-btn px-2.5 py-1.5 rounded-lg text-[12px] font-bold transition-all '
            + (active ? 'bg-brand-500 text-white shadow-sm' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600');
    });

    // 定位弹窗
    popup.style.top = `${rect.bottom + 8}px`;
    popup.style.right = `${window.innerWidth - rect.right}px`;
    popup.classList.remove('hidden');

    // 点击其他地方关闭
    setTimeout(() => {
        document.addEventListener('click', closeWidgetMenuOnOutsideClick, { once: true });
    }, 10);
}

function closeWidgetMenuOnOutsideClick(e) {
    const popup = document.getElementById('widget-menu-popup');
    if (!popup.contains(e.target)) {
        hideWidgetMenu();
    } else {
        setTimeout(() => document.addEventListener('click', closeWidgetMenuOnOutsideClick, { once: true }), 10);
    }
}

function hideWidgetMenu() {
    const popup = document.getElementById('widget-menu-popup');
    popup.classList.add('hidden');
    currentMenuWidgetId = null;
}

function setWidgetSizeFromMenu(w) {
    if (!currentMenuWidgetId) return;
    const el = document.querySelector(`[data-id="${currentMenuWidgetId}"]`);
    if (!el) return;
    const state = DashboardState.get();
    const { h } = Layout.parseSizeStr(state.sizes[currentMenuWidgetId] || el.dataset.defaultSize || '1x3');
    setWidgetSize(currentMenuWidgetId, `${w}x${h}`);
    hideWidgetMenu();
}

function hideWidgetFromMenu() {
    if (!currentMenuWidgetId) return;
    const el = document.querySelector(`[data-id="${currentMenuWidgetId}"]`);
    if (el) {
        el.classList.add('hidden');
        DashboardState.setVisible(currentMenuWidgetId, false);
    }
    hideWidgetMenu();
}

// 点击弹窗内部不关闭
document.getElementById('widget-menu-popup')?.addEventListener('click', e => e.stopPropagation());

// 导出到全局
window.toggleUserDropdown = toggleUserDropdown;
window.selectUser = selectUser;
window.changeUser = changeUser;
window.openDashManager = openDashManager;
window.closeDashManager = closeDashManager;
window.toggleWidgetVisibility = toggleWidgetVisibility;
window.resetDashboardLayout = resetDashboardLayout;
window.toggleWidgetMenu = toggleWidgetMenu;
window.setWidgetSizeFromMenu = setWidgetSizeFromMenu;
window.hideWidgetFromMenu = hideWidgetFromMenu;

// 启动
init();
