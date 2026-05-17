/**
 * dashboard/widgets.js
 * 所有 widget 数据请求 + DOM 渲染
 * 使用 escapeHtml() 防 XSS,使用 fetchJSON() 统一请求
 */

/* ---- 全局配置(由模板注入) ---- */
let embyBaseUrl = '';
let embyServerId = '';
function setEmbyConfig(url, serverId) { embyBaseUrl = url; embyServerId = serverId; }

/* ---- 自定义输入对话框 ---- */
function showDashInputDialog(options) {
    const { title = '输入', placeholder = '', defaultValue = '', onConfirm } = options;

    // 创建遮罩层
    const overlay = document.createElement('div');
    overlay.className = 'fixed inset-0 z-[300] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4';
    overlay.id = 'dash-input-dialog-overlay';

    // 创建对话框
    overlay.innerHTML = `
        <div class="bg-white dark:bg-[#1C1C1E] rounded-2xl shadow-2xl w-full max-w-sm border border-gray-100 dark:border-white/10 transform transition-all duration-300 scale-95 opacity-0" id="dash-input-dialog-content">
            <div class="px-6 py-4 border-b border-gray-100 dark:border-white/5">
                <h3 class="text-[16px] font-bold text-gray-800 dark:text-gray-100">${escapeHtml(title)}</h3>
            </div>
            <div class="p-6">
                <input type="text" id="dash-input-dialog-input" value="${escapeHtml(defaultValue)}" placeholder="${escapeHtml(placeholder)}" class="w-full px-4 py-3 rounded-xl border border-gray-200/80 dark:border-white/10 bg-gray-50 dark:bg-black/20 focus:ring-2 focus:ring-brand-500 outline-none text-[14px] transition-all shadow-sm dark:text-white">
            </div>
            <div class="px-6 py-4 border-t border-gray-100 dark:border-white/5 bg-gray-50/50 dark:bg-black/20 rounded-b-2xl flex justify-end gap-3">
                <button id="dash-input-dialog-cancel" class="px-5 py-2.5 bg-gray-100 dark:bg-[#2C2C2E] text-gray-600 dark:text-gray-300 rounded-xl text-[13px] font-bold hover:bg-gray-200 dark:hover:bg-[#3A3A3C] transition-colors">取消</button>
                <button id="dash-input-dialog-confirm" class="px-6 py-2.5 bg-brand-500 text-white rounded-xl text-[13px] font-bold hover:bg-brand-600 transition-colors shadow-md shadow-brand-500/20">确定</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    // 获取元素
    const content = overlay.querySelector('#dash-input-dialog-content');
    const input = overlay.querySelector('#dash-input-dialog-input');
    const cancelBtn = overlay.querySelector('#dash-input-dialog-cancel');
    const confirmBtn = overlay.querySelector('#dash-input-dialog-confirm');

    // 动画进入
    requestAnimationFrame(() => {
        content.classList.remove('scale-95', 'opacity-0');
        content.classList.add('scale-100', 'opacity-100');
    });

    // 聚焦输入框
    setTimeout(() => input.focus(), 100);

    // 关闭函数
    const close = () => {
        content.classList.remove('scale-100', 'opacity-100');
        content.classList.add('scale-95', 'opacity-0');
        setTimeout(() => overlay.remove(), 200);
    };

    // 事件绑定
    cancelBtn.onclick = close;
    confirmBtn.onclick = () => {
        const value = input.value;
        close();
        if (onConfirm) onConfirm(value);
    };
    input.onkeydown = (e) => {
        if (e.key === 'Enter') {
            confirmBtn.click();
        } else if (e.key === 'Escape') {
            close();
        }
    };
    overlay.onclick = (e) => {
        if (e.target === overlay) close();
    };
}

/* ---- 导航跳转 ---- */
function jumpToEmby(itemId) {
    if (!embyBaseUrl) { alert('提示: 未在设置中配置 Emby 地址。'); return; }
    window.open(`${embyBaseUrl}/web/index.html#!/item?id=${itemId}&serverId=${embyServerId}`, '_blank');
}
function jumpToLibrary(libraryId) {
    if (!embyBaseUrl) return;
    window.open(`${embyBaseUrl}/web/index.html#!/videos?serverId=${embyServerId}&parentId=${libraryId}`, '_blank');
}
function jumpToUserInsight(userId) { window.location.href = `/details?uid=${userId}`; }

/* ---- 天气(后端缓存,前端直接调用) ---- */
let _weatherGreeting = '';  // 自定义问候语(从后端加载)
let _weatherGreetingLoaded = false;  // 是否已加载

function setWeatherCity() {
    const current = localStorage.getItem('ep_weather_city') || '';
    showDashInputDialog({
        title: '设置城市',
        placeholder: '请输入城市名(如:北京、上海、Tokyo)',
        defaultValue: current,
        onConfirm: (city) => {
            if (city && city.trim() !== '') {
                localStorage.setItem('ep_weather_city', city.trim());
                // 强制刷新后端缓存
                fetchJSON('/api/system/weather/refresh?city=' + encodeURIComponent(city.trim()), { method: 'POST' })
                    .then(() => fetchWeather(true))
                    .catch(() => fetchWeather(true));
            }
        }
    });
}

function setWeatherGreeting() {
    const current = _weatherGreeting || '';
    showDashInputDialog({
        title: '修改称呼',
        placeholder: '请输入自定义称呼(如:主人、小明)',
        defaultValue: current,
        onConfirm: (name) => {
            if (name !== null) {
                _weatherGreeting = name.trim();
                _weatherGreetingLoaded = true;
                // 保存到后端配置
                fetchJSON('/api/settings/weather_greeting', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ weather_greeting: _weatherGreeting })
                }).then(() => {
                    updateWeatherGreeting();
                }).catch(() => {
                    updateWeatherGreeting();
                });
            }
        }
    });
}

function updateWeatherGreeting() {
    const hour = new Date().getHours();
    let timeGreeting = '你好';
    if (hour < 6) timeGreeting = '夜深了';
    else if (hour < 12) timeGreeting = '早上好';
    else if (hour < 18) timeGreeting = '下午好';
    else timeGreeting = '晚上好';

    const name = _weatherGreeting || '管家';
    const greetingEl = document.getElementById('weather-greeting');
    if (greetingEl) {
        greetingEl.textContent = timeGreeting + ',' + name;
    }
}

// 从后端加载问候语配置
function loadWeatherGreeting() {
    return fetchJSON('/api/settings').then(res => {
        if (res.status === 'success' && res.data.weather_greeting) {
            _weatherGreeting = res.data.weather_greeting;
        }
        _weatherGreetingLoaded = true;
    }).catch(() => {
        _weatherGreetingLoaded = true;
    });
}

// 刷新按钮(带动画)
function refreshWeatherBtn(btn) {
    const icon = btn.querySelector('i');
    if (icon.classList.contains('animate-spin')) return;  // 防止重复点击

    icon.classList.add('animate-spin');

    // 强制刷新后端缓存
    const city = localStorage.getItem('ep_weather_city') || '北京';
    fetchJSON('/api/system/weather/refresh?city=' + encodeURIComponent(city), { method: 'POST' })
        .then(() => fetchWeather(true))
        .catch(() => fetchWeather(true))
        .finally(() => {
            setTimeout(() => {
                icon.classList.remove('animate-spin');
            }, 500);
        });
}

function fetchWeather(forceRefresh = false) {
    const city = localStorage.getItem('ep_weather_city') || '北京';
    const cityEl = document.getElementById('weather-city');
    if (cityEl) cityEl.textContent = city;

    // 🔥 每次都重新加载问候语(确保跨设备同步)
    loadWeatherGreeting().finally(() => {
        updateWeatherGreeting();
    });

    // 🔥 后端已有缓存,前端直接调用
    return fetchJSON(`/api/system/weather?city=${encodeURIComponent(city)}`, { noCache: true })
        .then(json => {
            if (!json.success || !json.data) throw new Error('no data');
            const current = json.data.current_condition[0];
            applyWeatherData(current);
        })
        .catch(() => { document.getElementById('weather-desc').textContent = '数据拉取失败'; });
}

function applyWeatherData(current) {
    document.getElementById('weather-temp').textContent = current.temp_C + '°';
    document.getElementById('weather-humidity').textContent = current.humidity + '%';

    let desc = '';

    // 优先使用 lang_zh(和风/高德天气返回的中文描述)
    if (current.lang_zh && current.lang_zh[0] && current.lang_zh[0].value) {
        desc = current.lang_zh[0].value;
    }
    // 其次检查 weatherDesc 是否已经是中文
    else if (current.weatherDesc && current.weatherDesc[0] && current.weatherDesc[0].value) {
        const rawDesc = current.weatherDesc[0].value;
        // 检查是否包含中文字符
        if (/[\u4e00-\u9fa5]/.test(rawDesc)) {
            desc = rawDesc;
        } else {
            // 英文描述,尝试翻译
            const descMap = {
                Clear:'晴朗', Sunny:'晴天', 'Partly cloudy':'多云', Cloudy:'阴天', Overcast:'阴天',
                Mist:'薄雾', Rain:'有雨', 'Light rain':'小雨', Showers:'阵雨', Snow:'下雪',
                'Heavy rain':'大雨', Fog:'大雾', 'Patchy rain possible':'局部小雨',
                'Thundery outbreaks possible':'局部雷雨', 'Blizzard':'暴风雪', 'Freezing fog':'冻雾',
                'Patchy light drizzle':'局部小毛毛雨', 'Light drizzle':'毛毛雨',
                'Freezing drizzle':'冻毛毛雨', 'Heavy freezing drizzle':'大冻毛毛雨',
                'Patchy light rain':'局部小雨', 'Moderate rain at times':'时有中雨',
                'Moderate rain':'中雨', 'Light freezing rain':'小冻雨',
                'Moderate or heavy freezing rain':'中到大冻雨', 'Light sleet':'小雨夹雪',
                'Moderate or heavy sleet':'中到大雨夹雪', 'Patchy light snow':'局部小雪',
                'Light snow':'小雪', 'Patchy moderate snow':'局部中雪',
                'Moderate snow':'中雪', 'Patchy heavy snow':'局部大雪',
                'Heavy snow':'大雪', 'Ice pellets':'冰粒',
                'Light rain shower':'小阵雨', 'Moderate or heavy rain shower':'中到大阵雨',
                'Torrential rain shower':'暴雨', 'Light sleet showers':'小雨夹雪阵雨',
                'Moderate or heavy sleet showers':'中到大雨夹雪阵雨', 'Light snow showers':'小阵雪',
                'Moderate or heavy snow showers':'中到大阵雪', 'Patchy light rain with thunder':'局部小雨伴雷',
                'Moderate or heavy rain with thunder':'中到大雨伴雷', 'Patchy light snow with thunder':'局部小雪伴雷',
                'Moderate or heavy snow with thunder':'中到大雪伴雷'
            };
            desc = descMap[rawDesc] || rawDesc;
        }
    }

    // 最终兜底
    if (!desc) desc = '未知';

    document.getElementById('weather-desc').textContent = desc;
    document.getElementById('weather-icon').textContent = getWeatherIcon(current.weatherDesc ? current.weatherDesc[0].value : '');
}

/* ---- 系统监控(缓存优先 + 后台刷新) ---- */
const SYSMON_CACHE_KEY = 'ep_system_monitor_cache';
const SYSMON_CACHE_TTL = 60000; // 1分钟缓存

function fetchSystemMonitor() {
    const setBar = (id, val) => {
        const bar = document.getElementById(`${id}-bar`);
        const txt = document.getElementById(`${id}-val`);
        if (!bar || !txt) return;
        bar.style.width = `${val}%`;
        txt.textContent = `${val}%`;
        bar.className = 'h-1.5 rounded-full transition-all duration-1000 ease-out ';
        if (val > 85) bar.className += 'bg-red-500';
        else if (id.includes('cpu')) bar.className += 'bg-indigo-500';
        else if (id.includes('ram')) bar.className += 'bg-emerald-500';
        else bar.className += 'bg-amber-500';
    };

    // 🔥 先从缓存读取,立即显示旧数据
    try {
        const cached = JSON.parse(localStorage.getItem(SYSMON_CACHE_KEY));
        if (cached && cached.data) {
            setBar('sys-cpu', cached.data.cpu);
            setBar('sys-ram', cached.data.memory);
            setBar('sys-disk', cached.data.disk);
        }
    } catch (_) {}

    // 🔥 后台请求新数据
    const options = { noCache: true };
    if (window._dashboardAbortController && window._dashboardAbortController.signal) {
        options.signal = window._dashboardAbortController.signal;
    }
    return fetchJSON('/api/system/monitor', options)
        .then(json => {
            if (json.status === 'success') {
                const data = {
                    cpu: Math.round(json.data.cpu),
                    memory: Math.round(json.data.memory),
                    disk: Math.round(json.data.disk)
                };
                setBar('sys-cpu', data.cpu);
                setBar('sys-ram', data.memory);
                setBar('sys-disk', data.disk);
                // 🔥 更新缓存
                localStorage.setItem(SYSMON_CACHE_KEY, JSON.stringify({ data, ts: Date.now() }));
            }
        }).catch(e => {
            if (e.name !== 'AbortError') {
                // 只处理非取消错误
            }
        });
}

/* ---- 仪表盘核心数据(带 localStorage 缓存 5 分钟) ---- */
const DASH_CACHE_KEY = 'ep_dashboard_data_cache';
const DASH_CACHE_TTL = 300000;

async function fetchDashboardData(userId) {
    const cacheKey = DASH_CACHE_KEY + '_' + userId;
    try {
        let data = null;
        try {
            const cached = JSON.parse(localStorage.getItem(cacheKey));
            if (cached && Date.now() - cached.ts < DASH_CACHE_TTL) data = cached.data;
        } catch (_) {}
        if (!data) {
            const json = await fetchJSON(`/api/stats/dashboard?user_id=${userId}`, { noCache: true });
            if (json.status !== 'success') return;
            data = json.data;
            localStorage.setItem(cacheKey, JSON.stringify({ data, ts: Date.now() }));
        }
        const lib = data.library || {};
        const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setText('lib-movies', lib.movie || '0');
        setText('lib-series', lib.series || '0');
        setText('lib-episodes', lib.episode || '0');
        setText('stat-plays', data.total_plays || '0');
        setText('stat-users', data.active_users || '0');
        setText('stat-duration', Math.round((data.total_duration || 0) / 3600) || '0');
    } catch (_) {}
}

/* ---- 媒体库列表(stale-while-revalidate 缓存) ---- */
const LIB_CACHE_KEY = 'ep_libraries_cache';
const LIB_CACHE_TTL = 600000; // 10分钟

// 手动刷新媒体库
let _librariesRefreshTs = 0;  // 刷新时间戳

function refreshLibraries(event) {
    event.stopPropagation();
    const icon = document.getElementById('libraries-refresh-icon');
    if (icon) icon.classList.add('fa-spin');

    // 更新刷新时间戳,强制图片重新加载
    _librariesRefreshTs = Date.now();

    // 清除前端缓存
    localStorage.removeItem(LIB_CACHE_KEY);

    // 清除后端图片缓存
    fetchJSON('/api/proxy/clear_cache', { method: 'POST' })
        .catch(() => {})  // 忽略错误,继续刷新
        .finally(() => {
            // 重新获取媒体库
            fetchLibraries().finally(() => {
                setTimeout(() => {
                    if (icon) icon.classList.remove('fa-spin');
                }, 500);
            });
        });
}

async function fetchLibraries() {
    const container = document.getElementById('library-container');
    // 先尝试缓存秒出
    try {
        const cached = JSON.parse(localStorage.getItem(LIB_CACHE_KEY));
        if (cached && cached.html) {
            container.innerHTML = cached.html;
            requestAnimationFrame(() => fitGridContent('library-container'));
            // 缓存未过期就不刷新
            if (Date.now() - cached.ts < LIB_CACHE_TTL) return;
        }
    } catch (_) {}
    // 请求新数据
    await fetchAndRender('/api/stats/libraries', container, (json) => {
        let html = '';
        json.data.forEach(lib => {
            // 🔥 添加版本参数,使用 ImageTag + 刷新时间戳
            const imageTag = lib.ImageTag || '';
            const tsParam = _librariesRefreshTs ? `&_ts=${_librariesRefreshTs}` : '';
            const versionParam = imageTag ? `?v=${imageTag}${tsParam}` : (tsParam ? `?${tsParam.slice(1)}` : '');
            const imgUrl = `/api/proxy/image/${encodeURIComponent(lib.Id)}/primary${versionParam}`;
            const name = escapeHtml(lib.Name);
            html += `<div onclick="jumpToLibrary('${escapeHtml(lib.Id)}')" class="lib-card relative aspect-video rounded-2xl overflow-hidden cursor-pointer bg-gray-200 dark:bg-apple-hoverDark">
                <img src="${imgUrl}" class="w-full h-full object-cover transition duration-500 opacity-90 hover:opacity-100 hover:scale-105" onerror="this.src='/static/img/logo-app.png'" loading="lazy">
                <div class="absolute bottom-0 inset-x-0 p-3 pb-3 flex justify-center items-end bg-gradient-to-t from-black/60 to-transparent"><h4 class="text-white font-semibold text-sm md:text-[15px] truncate w-full text-center tracking-widest drop-shadow-md">${name}</h4></div>
            </div>`;
        });
        container.innerHTML = html;
        localStorage.setItem(LIB_CACHE_KEY, JSON.stringify({ html, ts: Date.now() }));
        requestAnimationFrame(() => fitGridContent('library-container'));
    }, { checkFn: j => j.status === 'success' && j.data && j.data.length > 0, emptyText: '暂无媒体库' });
}

/* ---- 天气图标映射(补全) ---- */
function getWeatherIcon(desc) {
    const d = desc || '';
    if (d.includes('Rain') || d.includes('Showers') || d.includes('雨')) return '🌧️';
    if (d.includes('Clear') || d.includes('Sunny') || d === '晴') return '☀️';
    if (d.includes('Cloud') || d.includes('多云') || d.includes('阴')) return '☁️';
    if (d.includes('Snow') || d.includes('雪')) return '❄️';
    if (d.includes('雾') || d.includes('霾') || d.includes('Fog') || d.includes('Mist')) return '🌫️';
    if (d.includes('雷') || d.includes('Thunder')) return '⛈️';
    return '🌤️';
}

/* ---- 最近入库(stale-while-revalidate 缓存) ---- */
const LATEST_CACHE_KEY = 'ep_latest_cache_v2';  // 🔥 v2 强制清理旧缓存
const LATEST_CACHE_TTL = 600000;

function buildLatestHtml(data) {
    let html = '';
    data.forEach(item => {
        // 🔥 封面优先 TMDB URL,否则使用代理 API
        const poster = item.Poster || '';
        let imgUrl;
        if (poster && poster.includes('image.tmdb.org')) {
            imgUrl = poster;
        } else {
            // 🔥 添加版本参数,使用 ImageTag 作为版本标识
            const imageTag = item.ImageTag || '';
            const versionParam = imageTag ? `?v=${imageTag}` : '';
            imgUrl = `/api/proxy/image/${encodeURIComponent(item.Id)}/primary${versionParam}`;
        }
        let title = item.Name;
        let badge = '';
        let titleSuffix = ''; // 标题后缀:集数范围
        // 🔥 处理剧集集数范围显示 - Type 是 'Series' 而不是 'Episode'
        if (item.Type === 'Series' && (item.SeasonIndex != null || item.SeasonIndex !== undefined)) {
            const epCount = item.EpisodeCount || 1;
            const epMin = item.EpisodeMin;
            const epMax = item.EpisodeMax;
            const seasonLabel = item.SeasonIndex != null ? `S${String(item.SeasonIndex).padStart(2,'0')}` : '';
            // 多集入库:显示 +N 徽章,标题显示完整集数范围
            if (epCount > 1 && epMin != null && epMax != null) {
                badge = `<span class="absolute top-1.5 right-1.5 bg-brand-500/90 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-md shadow-sm z-10">+${epCount}</span>`;
                titleSuffix = `<span class="text-[10px] text-gray-400 dark:text-gray-500 ml-1 font-mono">${seasonLabel}E${String(epMin).padStart(2,'0')}-E${String(epMax).padStart(2,'0')}</span>`;
            } else if (epMin != null) {
                // 单集或连续集
                if (epMin === epMax || epCount === 1) {
                    badge = `<span class="absolute top-1.5 right-1.5 bg-black/50 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-md z-10">${seasonLabel}E${String(epMin).padStart(2,'0')}</span>`;
                } else if (epMax != null) {
                    badge = `<span class="absolute top-1.5 right-1.5 bg-black/50 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-md z-10">${seasonLabel}E${String(epMin).padStart(2,'0')}-${String(epMax).padStart(2,'0')}</span>`;
                    titleSuffix = `<span class="text-[10px] text-gray-400 dark:text-gray-500 ml-1 font-mono">${seasonLabel}E${String(epMin).padStart(2,'0')}-E${String(epMax).padStart(2,'0')}</span>`;
                }
            } else if (item.SeasonIndex != null) {
                // 只有季信息
                badge = `<span class="absolute top-1.5 right-1.5 bg-black/50 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-md z-10">S${String(item.SeasonIndex).padStart(2,'0')}</span>`;
            }
            if (item.SeriesName) {
                title = item.SeriesName;
            }
        }
        html += `<div onclick="jumpToEmby('${escapeHtml(item.Id)}')" class="poster-card cursor-pointer relative overflow-hidden">
            ${badge}
            <div class="poster-img-wrap bg-gray-100 dark:bg-apple-hoverDark border border-gray-100 dark:border-white/5">
                <img src="${imgUrl}" loading="lazy" class="transition-all duration-300 opacity-0" onload="this.style.opacity='1'" onerror="this.src='/static/img/logo-app.png';this.style.opacity='1'">
            </div>
            <div class="poster-title-wrap"><h4 class="poster-title text-[11px] font-medium text-gray-900 dark:text-gray-100 leading-tight transition-colors line-clamp-2">${escapeHtml(title)}${titleSuffix}</h4></div>
        </div>`;
    });
    return html;
}

async function fetchLatest() {
    const container = document.getElementById('latest-container');

    // 🔥 先从缓存渲染(秒出)
    let cachedHtml = '';
    try {
        const cached = JSON.parse(localStorage.getItem(LATEST_CACHE_KEY));
        if (cached && cached.html) {
            cachedHtml = cached.html;
            container.innerHTML = cachedHtml;
            requestAnimationFrame(() => fitGridContent('latest-container'));
        }
    } catch (_) {}

    // 🔥 使用全局 AbortSignal(如果存在)
    const options = {};
    if (window._dashboardAbortController && window._dashboardAbortController.signal) {
        options.signal = window._dashboardAbortController.signal;
    }

    // 🔥 不 await,让请求异步进行(不阻塞)
    fetchAndRender('/api/stats/latest?limit=60', container, (json) => {
        const html = buildLatestHtml(json.data);
        if (html !== cachedHtml) {
            container.innerHTML = html;
            localStorage.setItem(LATEST_CACHE_KEY, JSON.stringify({ html, ts: Date.now() }));
            requestAnimationFrame(() => fitGridContent('latest-container'));
        }
    }, { checkFn: j => j.status === 'success' && j.data && j.data.length > 0, ...options });
}

/* ---- 最近播放(缓存优先 + 后台刷新) ---- */
const RECENT_CACHE_KEY = 'ep_recent_play_cache';
const RECENT_CACHE_TTL = 300000; // 5分钟(播放变化比入库频繁)

function buildRecentHtml(data) {
    let html = '';
    data.slice(0, 60).forEach(item => {
        // 🔥 添加版本参数,使用 ImageTag 作为版本标识
        const imageTag = item.ImageTag || '';
        const versionParam = imageTag ? `?v=${imageTag}` : '';
        const imgUrl = `/api/proxy/image/${encodeURIComponent(item.ItemId)}/primary${versionParam}`;
        html += `<div onclick="jumpToEmby('${escapeHtml(item.ItemId)}')" class="poster-card cursor-pointer">
            <div class="poster-img-wrap bg-gray-100 dark:bg-apple-hoverDark border border-gray-100 dark:border-white/5">
                <img src="${imgUrl}" loading="lazy" class="transition-all duration-300 opacity-0" onload="this.style.opacity='1'" onerror="this.src='/static/img/logo-app.png';this.style.opacity='1'">
                <div class="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/60 to-transparent flex items-end"><p class="text-[10px] text-white font-medium truncate flex items-center w-full drop-shadow-md"><i class="fa-solid fa-play text-[8px] mr-1.5 opacity-80"></i>${escapeHtml(item.UserName)}</p></div>
            </div>
            <div class="poster-title-wrap"><h4 class="poster-title text-[11px] font-medium text-gray-900 dark:text-gray-100 leading-tight transition-colors line-clamp-2">${escapeHtml(item.DisplayName || item.ItemName)}</h4></div>
        </div>`;
    });
    return html;
}

async function fetchRecentActivity(userId) {
    const container = document.getElementById('recent-container');
    const cacheKey = RECENT_CACHE_KEY + '_' + userId;

    // 🔥 先从缓存渲染(秒出)
    let cachedHtml = '';
    try {
        const cached = JSON.parse(localStorage.getItem(cacheKey));
        if (cached && cached.html) {
            cachedHtml = cached.html;
            container.innerHTML = cachedHtml;
            requestAnimationFrame(() => fitGridContent('recent-container'));
        }
    } catch (_) {}

    // 🔥 使用全局 AbortSignal(如果存在)
    const options = {};
    if (window._dashboardAbortController && window._dashboardAbortController.signal) {
        options.signal = window._dashboardAbortController.signal;
    }

    // 🔥 不 await,让请求异步进行(不阻塞)
    fetchAndRender(`/api/stats/recent?user_id=${userId}`, container, (json) => {
        const html = buildRecentHtml(json.data);
        if (html !== cachedHtml) {
            container.innerHTML = html;
            localStorage.setItem(cacheKey, JSON.stringify({ html, ts: Date.now() }));
            requestAnimationFrame(() => fitGridContent('recent-container'));
        }
    }, { checkFn: j => j.status === 'success' && j.data && j.data.length > 0, ...options });
}

/* ---- 白金观影榜 ---- */
let currentTopPeriod = 'all';
function switchTopUsers(period) {
    currentTopPeriod = period;
    ['yesterday', 'day', 'week', 'month', 'all'].forEach(p => {
        const btn = document.getElementById(`top-btn-${p}`);
        if (!btn) return;
        btn.className = p === period
            ? 'px-2 py-1 rounded bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-white transition font-medium'
            : 'px-2 py-1 rounded text-gray-500 hover:text-gray-900 dark:hover:text-white transition';
    });
    fetchTopUsers(period);
}

async function fetchTopUsers(period) {
    const container = document.getElementById('top-users-container');
    container.innerHTML = '<div class="flex justify-center items-center h-32"><i class="fa-solid fa-spinner fa-spin text-gray-300"></i></div>';
    // 🔥 不 await,使用 AbortSignal
    fetchAndRender(`/api/stats/top_users_list?period=${period}`, container, (json) => {
        let html = '';
        json.data.forEach((user, index) => {
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
                <div class="flex items-center pl-3"><p class="text-[14px] font-semibold text-gray-900 dark:text-white tracking-tight text-right w-12">${(user.TotalTime/3600).toFixed(1)}<span class="text-[9px] font-normal opacity-60 ml-0.5">h</span></p><i class="fa-solid fa-chevron-right text-[10px] text-gray-300 dark:text-gray-600 user-rank-arrow ml-2"></i></div>
            </div>`;
        });
        container.innerHTML = html;
    }, { checkFn: j => j.status === 'success' && j.data && j.data.length > 0, signal: getDashboardSignal() });
}

/* ---- 今日追剧日历 ---- */
async function fetchTodayCalendar() {
    const c = document.getElementById('calendar-today-container');
    // 🔥 使用 AbortSignal
    try {
        const json = await fetchJSON('/api/calendar/weekly', { signal: getDashboardSignal() });
        if (json.error || !json.days) { c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-8"><i class="fa-solid fa-key text-gray-300 text-2xl mb-2 block"></i>未配置 TMDB Key</div>'; return; }
        const today = json.days.find(d => d.is_today);
        if (!today || !today.items || today.items.length === 0) { c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-8"><i class="fa-solid fa-couch text-gray-300 text-2xl mb-2 block"></i>今天没有剧集更新</div>'; return; }
        let html = '';
        today.items.forEach(ep => {
            const stMap = { ready: { cls: 'bg-emerald-500', label: '已入库' }, missing: { cls: 'bg-red-500', label: '缺失' }, today: { cls: 'bg-amber-500', label: '今日' }, upcoming: { cls: 'bg-gray-400', label: '待播' } };
            const s = stMap[ep.status] || stMap.upcoming;
            const epNum = typeof ep.episode === 'string' ? `E${ep.episode}` : `E${String(ep.episode).padStart(2,'0')}`;
            const poster = ep.poster_path ? `https://image.tmdb.org/t/p/w92${ep.poster_path}` : '/static/img/logo-app.png';
            html += `<div class="flex items-center gap-3 p-2 rounded-xl hover:bg-gray-50 dark:hover:bg-white/5 transition-colors">
                <div class="w-10 h-14 rounded-lg overflow-hidden bg-gray-100 dark:bg-gray-800 shrink-0 shadow-sm"><img src="${poster}" class="w-full h-full object-cover" onerror="this.src='/static/img/logo-app.png'"></div>
                <div class="flex-1 min-w-0">
                    <p class="text-[13px] font-semibold text-gray-800 dark:text-gray-200 truncate">${escapeHtml(ep.series_name)}</p>
                    <p class="text-[11px] text-gray-500 mt-0.5">S${String(ep.season).padStart(2,'0')}${epNum}</p>
                </div>
                <span class="text-[9px] font-bold text-white px-2 py-0.5 rounded-full ${s.cls} shrink-0 shadow-sm">${s.label}</span>
            </div>`;
        });
        c.innerHTML = html;
    } catch (e) {
        if (e.name !== 'AbortError') {
            c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-8">加载失败</div>';
        }
    }
}

/* ---- 媒体库质量 ---- */
async function fetchQualityChart() {
    const c = document.getElementById('quality-container');
    // 🔥 不 await,使用 AbortSignal
    fetchAndRender('/api/insight/quality', c, (json) => {
        const m = json.data.movies;
        const items = [
            { label: '4K', count: (m['4k']||[]).length, color: 'bg-cyan-500', bg: 'bg-cyan-100 dark:bg-cyan-500/15' },
            { label: '1080P', count: (m['1080p']||[]).length, color: 'bg-blue-500', bg: 'bg-blue-100 dark:bg-blue-500/15' },
            { label: '720P', count: (m['720p']||[]).length, color: 'bg-violet-500', bg: 'bg-violet-100 dark:bg-violet-500/15' },
            { label: 'SD', count: (m['sd']||[]).length, color: 'bg-gray-400', bg: 'bg-gray-100 dark:bg-gray-500/15' }
        ];
        const total = items.reduce((a, b) => a + b.count, 0) || 1;
        let html = '<div class="w-full space-y-3">';
        items.forEach(it => {
            const pct = Math.round(it.count / total * 100);
            html += `<div><div class="flex justify-between text-[11px] font-bold mb-1"><span class="text-gray-600 dark:text-gray-400">${it.label}</span><span class="text-gray-800 dark:text-gray-200 font-mono">${it.count} <span class="text-gray-400 font-normal">(${pct}%)</span></span></div><div class="w-full h-2 rounded-full ${it.bg} overflow-hidden"><div class="${it.color} h-2 rounded-full transition-all duration-700 ease-out" style="width:${pct}%"></div></div></div>`;
        });
        const hevc = (m['hevc']||[]).length; const h264 = (m['h264']||[]).length;
        if (hevc + h264 > 0) {
            html += `<div class="flex gap-3 mt-2 pt-2 border-t border-gray-100 dark:border-white/5"><span class="text-[10px] font-bold text-gray-500"><i class="fa-solid fa-microchip text-[9px] mr-1 text-emerald-500"></i>HEVC ${hevc}</span><span class="text-[10px] font-bold text-gray-500"><i class="fa-solid fa-microchip text-[9px] mr-1 text-blue-500"></i>H.264 ${h264}</span></div>`;
        }
        html += '</div>';
        c.innerHTML = html;
    }, { checkFn: j => j.status === 'success', signal: getDashboardSignal() });
}

/* ---- 终端分布 ---- */
async function fetchClientsChart() {
    const c = document.getElementById('clients-container');
    // 🔥 不 await,使用 AbortSignal
    fetchAndRender('/api/clients/data', c, (json) => {
        const pie = json.charts.pie;
        const colors = ['bg-violet-500','bg-pink-500','bg-amber-500','bg-emerald-500','bg-blue-500','bg-red-500','bg-indigo-500','bg-teal-500'];
        const bgColors = ['bg-violet-100 dark:bg-violet-500/15','bg-pink-100 dark:bg-pink-500/15','bg-amber-100 dark:bg-amber-500/15','bg-emerald-100 dark:bg-emerald-500/15','bg-blue-100 dark:bg-blue-500/15','bg-red-100 dark:bg-red-500/15','bg-indigo-100 dark:bg-indigo-500/15','bg-teal-100 dark:bg-teal-500/15'];
        const total = pie.data.reduce((a, b) => a + b, 0) || 1;
        let html = '<div class="w-full space-y-3">';
        pie.labels.slice(0, 5).forEach((label, i) => {
            const count = pie.data[i]; const pct = Math.round(count / total * 100);
            html += `<div><div class="flex justify-between text-[11px] font-bold mb-1"><span class="text-gray-600 dark:text-gray-400 truncate">${escapeHtml(label)}</span><span class="text-gray-800 dark:text-gray-200 font-mono shrink-0 ml-2">${count} <span class="text-gray-400 font-normal">(${pct}%)</span></span></div><div class="w-full h-2 rounded-full ${bgColors[i % bgColors.length]} overflow-hidden"><div class="${colors[i % colors.length]} h-2 rounded-full transition-all duration-700 ease-out" style="width:${pct}%"></div></div></div>`;
        });
        html += '</div>';
        c.innerHTML = html;
    }, { checkFn: j => j.status === 'success' && j.charts, signal: getDashboardSignal() });
}

/* ---- 外部服务连通性(缓存优先 + 手动刷新) ---- */
const CONNECTIVITY_CACHE_KEY = 'ep_connectivity_cache';
const CONNECTIVITY_CACHE_TTL = 300000; // 5分钟缓存

function renderConnectivity(data) {
    const c = document.getElementById('connectivity-container');
    if (!c) return;

    const svc = (icon, iconCls, name, ok, ping) => {
        const statusDot = ok ? 'bg-emerald-500 shadow-emerald-500/50' : 'bg-red-500 shadow-red-500/50';
        const latency = ok ? `<span class="text-[11px] font-bold font-mono text-emerald-600 dark:text-emerald-400">${ping}<span class="text-[9px] font-normal ml-0.5">ms</span></span>` : '<span class="text-[11px] font-bold text-red-500">离线</span>';
        return `<div class="flex items-center gap-2.5 p-2 rounded-xl bg-gray-50/80 dark:bg-white/[0.03] border border-gray-100/50 dark:border-white/5"><div class="w-7 h-7 rounded-lg ${iconCls} flex items-center justify-center shrink-0"><i class="${icon} text-white text-[11px]"></i></div><div class="flex-1 min-w-0"><p class="text-[11px] font-semibold text-gray-800 dark:text-gray-200 truncate">${escapeHtml(name)}</p></div><span class="inline-block w-1.5 h-1.5 rounded-full ${statusDot} shadow-sm mr-1 shrink-0"></span>${latency}</div>`;
    };
    const webhookTime = data.webhook.last_active === '暂无记录' ? '无记录' : data.webhook.last_active.slice(5,16).replace('T',' ');
    c.innerHTML = svc('fa-brands fa-telegram', 'bg-sky-500', 'Telegram', data.tg.ok, data.tg.ping)
        + svc('fa-solid fa-film', 'bg-amber-500', 'TMDB', data.tmdb.ok, data.tmdb.ping)
        + `<div class="flex items-center gap-2.5 p-2 rounded-xl bg-gray-50/80 dark:bg-white/[0.03] border border-gray-100/50 dark:border-white/5"><div class="w-7 h-7 rounded-lg bg-purple-500 flex items-center justify-center shrink-0"><i class="fa-solid fa-bolt text-white text-[11px]"></i></div><div class="flex-1"><p class="text-[11px] font-semibold text-gray-800 dark:text-gray-200">Webhook</p></div><span class="text-[10px] font-medium text-gray-500 font-mono truncate">${escapeHtml(webhookTime)}</span></div>`;
}

async function fetchConnectivity(forceRefresh = false) {
    const c = document.getElementById('connectivity-container');
    
    // 🔥 先从缓存读取并立即渲染（不管是否过期）
    let cachedData = null;
    let cacheTs = 0;
    try {
        const cached = JSON.parse(localStorage.getItem(CONNECTIVITY_CACHE_KEY));
        if (cached && cached.data) {
            cachedData = cached.data;
            cacheTs = cached.ts || 0;
            renderConnectivity(cachedData);  // ← 立即渲染缓存
        }
    } catch (_) {}
    
    // 🔥 如果强制刷新或缓存过期，后台刷新
    const cacheExpired = !cachedData || (Date.now() - cacheTs > CONNECTIVITY_CACHE_TTL);
    
    if (forceRefresh || cacheExpired) {
        try {
            const json = await fetchJSON('/api/system/network_check', { signal: getDashboardSignal() });
            if (!json.success) { 
                // 请求失败但有缓存，继续显示缓存
                if (!cachedData) {
                    c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-4">检测失败</div>'; 
                }
                return; 
            }
            // 🔥 保存缓存
            localStorage.setItem(CONNECTIVITY_CACHE_KEY, JSON.stringify({ data: json.data, ts: Date.now() }));
            renderConnectivity(json.data);
        } catch (e) {
            // 网络错误时，如果有缓存就继续显示缓存
            if (e.name !== 'AbortError' && !cachedData) {
                c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-4">网络异常</div>'; 
            }
        }
    }
}

// 🔥 手动刷新外部服务
function refreshConnectivity(event) {
    event.stopPropagation();
    const icon = document.getElementById('connectivity-refresh-icon');
    if (icon) icon.classList.add('fa-spin');
    fetchConnectivity(true).finally(() => {
        setTimeout(() => {
            if (icon) icon.classList.remove('fa-spin');
        }, 500);
    });
}

/* ---- 后台任务健康(带 localStorage 缓存 5 分钟) ---- */
const TASKS_CACHE_KEY = 'ep_tasks_cache';
const TASKS_CACHE_TTL = 300000;

async function fetchTasksHealth() {
    const c = document.getElementById('tasks-health-container');
    // 🔥 使用 AbortSignal
    try {
        let json = null;
        try {
            const cached = JSON.parse(localStorage.getItem(TASKS_CACHE_KEY));
            if (cached && Date.now() - cached.ts < TASKS_CACHE_TTL) json = cached.data;
        } catch (_) {}
        if (!json) {
            json = await fetchJSON('/api/tasks', { noCache: true, signal: getDashboardSignal() });
            localStorage.setItem(TASKS_CACHE_KEY, JSON.stringify({ data: json, ts: Date.now() }));
        }
        if (json.status !== 'success' || !json.data) { c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-8">暂无数据</div>'; return; }
        let allTasks = []; json.data.forEach(g => { if (g.tasks) allTasks = allTasks.concat(g.tasks); });
        if (allTasks.length === 0) { c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-8">暂无任务</div>'; return; }

        const failed = allTasks.filter(t => t.LastExecutionResult && t.LastExecutionResult.Status === 'Failed');
        const running = allTasks.filter(t => t.State === 'Running');
        const ok = allTasks.length - failed.length - running.length;

        // 状态统计
        let html = '<div class="flex items-center gap-2 mb-2 flex-wrap">';
        if (ok > 0) html += `<span class="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>${ok} 正常</span>`;
        if (running.length > 0) html += `<span class="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400"><span class="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse"></span>${running.length} 运行中</span>`;
        if (failed.length > 0) html += `<span class="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400"><span class="w-1.5 h-1.5 rounded-full bg-red-500"></span>${failed.length} 失败</span>`;
        html += '</div>';

        // 任务列表:失败优先,然后运行中,最后正常
        const priorityTasks = [...failed, ...running, ...allTasks.filter(t => !failed.includes(t) && !running.includes(t))].slice(0, 6);
        priorityTasks.forEach(t => {
            const isFailed = t.LastExecutionResult && t.LastExecutionResult.Status === 'Failed';
            const isRunning = t.State === 'Running';
            const dotCls = isRunning ? 'bg-blue-500 animate-pulse' : isFailed ? 'bg-red-500' : 'bg-emerald-500';
            html += `<div class="flex items-center gap-2 py-1 px-1"><span class="w-1.5 h-1.5 rounded-full ${dotCls} shrink-0"></span><span class="text-[11px] font-medium text-gray-700 dark:text-gray-300 truncate flex-1">${escapeHtml(t.Name || t.OriginalName)}</span></div>`;
        });
        c.innerHTML = html;
    } catch (e) {
        if (e.name !== 'AbortError') {
            c.innerHTML = '<div class="text-[13px] text-gray-400 text-center py-8">加载失败</div>';
        }
    }
}

/* ---- 入库统计 ---- */
const ADDED_STATS_CACHE_KEY = 'ep_added_stats_cache';
const ADDED_STATS_CACHE_TTL = 300000; // 5分钟

async function fetchAddedStats() {
    try {
        // 尝试使用缓存快速显示
        const cached = localStorage.getItem(ADDED_STATS_CACHE_KEY);
        if (cached) {
            const { data, ts } = JSON.parse(cached);
            if (data) {
                document.getElementById('added-week-total').textContent = data.total_this_week || '0';
                if (data.trend) {
                    renderAddedChart(data.trend);
                }
                // 缓存未过期则不刷新
                if (Date.now() - ts < ADDED_STATS_CACHE_TTL) return;
            }
        }

        // 请求新数据
        const json = await fetchJSON('/api/stats/recent_added');
        if (json.status === 'success' && json.data) {
            const data = json.data;
            document.getElementById('added-week-total').textContent = data.total_this_week || '0';
            if (data.trend) {
                renderAddedChart(data.trend);
            }
            localStorage.setItem(ADDED_STATS_CACHE_KEY, JSON.stringify({ data, ts: Date.now() }));
        }
    } catch (e) {
        console.error('[AddedStats] 加载失败:', e);
    }
}

/* ---- 导出到全局 ---- */
window.setEmbyConfig = setEmbyConfig;
window.jumpToEmby = jumpToEmby;
window.jumpToLibrary = jumpToLibrary;
window.jumpToUserInsight = jumpToUserInsight;
window.setWeatherCity = setWeatherCity;
window.fetchWeather = fetchWeather;
window.getWeatherIcon = getWeatherIcon;
window.fetchSystemMonitor = fetchSystemMonitor;
window.fetchDashboardData = fetchDashboardData;
window.fetchLibraries = fetchLibraries;
window.refreshLibraries = refreshLibraries;
window.fetchLatest = fetchLatest;
window.fetchRecentActivity = fetchRecentActivity;
window.switchTopUsers = switchTopUsers;
window.fetchTopUsers = fetchTopUsers;
window.fetchTodayCalendar = fetchTodayCalendar;
window.fetchQualityChart = fetchQualityChart;
window.fetchClientsChart = fetchClientsChart;
window.fetchConnectivity = fetchConnectivity;
window.refreshConnectivity = refreshConnectivity;
window.fetchConnectivity = fetchConnectivity;
window.fetchTasksHealth = fetchTasksHealth;
window.fetchAddedStats = fetchAddedStats;