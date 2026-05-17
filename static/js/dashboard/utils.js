/**
 * dashboard/utils.js
 * 公共工具函数 — fetchJSON(带缓存) / 安全 DOM / 网格计算 / 懒加载
 */

/* ---- 🔥 获取当前 AbortSignal（用于取消请求） ---- */
function getDashboardSignal() {
    if (window._dashboardAbortController && window._dashboardAbortController.signal) {
        return window._dashboardAbortController.signal;
    }
    return undefined;
}

/* ---- API 缓存层 ---- */
const _apiCache = {};
const DEFAULT_CACHE_TTL = 60000; // 60s

/**
 * 统一的 JSON 请求封装（带内存缓存 + AbortSignal 支持）
 * @param {string} url
 * @param {object} opts - fetch options + { cacheTTL: ms, noCache: bool, signal: AbortSignal }
 */
async function fetchJSON(url, opts = {}) {
    const { cacheTTL = DEFAULT_CACHE_TTL, noCache = false, signal, ...fetchOpts } = opts;
    
    // 只缓存 GET 请求
    if (!noCache && (!fetchOpts.method || fetchOpts.method === 'GET')) {
        const cached = _apiCache[url];
        if (cached && Date.now() - cached.ts < cacheTTL) {
            return cached.data;
        }
    }
    
    // 合并 signal 到 fetch options
    const finalOpts = { ...fetchOpts };
    if (signal) {
        finalOpts.signal = signal;
    }
    
    const res = await fetch(url, finalOpts);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    if (!noCache && (!fetchOpts.method || fetchOpts.method === 'GET')) {
        _apiCache[url] = { data: json, ts: Date.now() };
    }
    return json;
}

/** 清除指定 URL 或全部缓存 */
function clearApiCache(url) {
    if (url) delete _apiCache[url];
    else Object.keys(_apiCache).forEach(k => delete _apiCache[k]);
}

/**
 * 带 loading/error 状态的 fetch 封装
 * @param {string} url
 * @param {HTMLElement} container - 显示 loading/error 的容器
 * @param {Function} onSuccess - (data) => void，成功时的渲染回调
 * @param {object} opts - { emptyText, errorText, checkFn }
 */
async function fetchAndRender(url, container, onSuccess, opts = {}) {
    const { emptyText = '暂无数据', errorText = '加载失败', checkFn, signal } = opts;
    try {
        // 🔥 传递 signal 给 fetchJSON
        const json = await fetchJSON(url, { signal });
        if (checkFn && !checkFn(json)) {
            container.innerHTML = `<div class="text-[13px] text-gray-400 text-center py-8">${escapeHtml(emptyText)}</div>`;
            return null;
        }
        onSuccess(json);
        return json;
    } catch (e) {
        // 🔥 AbortError 不显示错误
        if (e.name === 'AbortError') {
            return null;
        }
        container.innerHTML = `<div class="text-[13px] text-gray-400 text-center py-8">${escapeHtml(errorText)}</div>`;
        return null;
    }
}

/** HTML 转义 — 防 XSS */
function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    return str.replace(/[&<>"']/g, c => map[c]);
}

/** 安全创建文本节点 */
function safeText(parent, text) {
    parent.appendChild(document.createTextNode(text));
}

/**
 * 网格内容溢出控制 — 按整行隐藏，绝不露出半截行
 * 用容器自身的实际高度（flex-1 撑开后的值），不硬编码偏移量
 */
function fitGridContent(containerId) {
    const container = document.getElementById(containerId);
    if (!container || container.children.length === 0) return;
    if (window.innerWidth < 768) {
        container.style.maxHeight = '';
        container.style.overflow = '';
        Array.from(container.children).forEach(child => { child.style.display = ''; });
        return;
    }

    // 先全部显示，清除之前的限制
    const children = Array.from(container.children);
    children.forEach(child => { child.style.display = ''; });
    container.style.maxHeight = 'none';
    container.style.overflow = 'visible';
    void container.offsetHeight;

    // 容器的实际可用高度 = widget 内部 flex 分配给它的高度
    // 直接读容器父级给它的空间，而不是硬编码 widget高度-80
    const widget = container.closest('.widget-item');
    if (!widget) return;
    const widgetRect = widget.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();
    // 可用高度 = widget 底边 - 容器顶边 - widget 底部 padding(24px)
    const availH = widgetRect.bottom - containerRect.top - 24;

    if (availH < 40) {
        // 不再隐藏容器，改为设置安全的最大高度
        container.style.maxHeight = '60px';
        container.style.overflow = 'auto';
        return;
    }
    container.style.display = '';

    const containerTop = containerRect.top;

    // 按行分组（同一行的子项 top 值相近，容差 3px）
    const rows = [];
    children.forEach(child => {
        const rect = child.getBoundingClientRect();
        const relTop = rect.top - containerTop;
        const relBottom = rect.bottom - containerTop;
        let row = rows.find(r => Math.abs(r.top - relTop) < 3);
        if (!row) {
            row = { top: relTop, bottom: relBottom, children: [] };
            rows.push(row);
        }
        row.bottom = Math.max(row.bottom, relBottom);
        row.children.push(child);
    });
    rows.sort((a, b) => a.top - b.top);

    // 找出能完整放下的最大行数（容差 5px，避免亚像素误差裁掉整行）
    let visibleRows = 0;
    for (let i = 0; i < rows.length; i++) {
        if (rows[i].bottom <= availH + 5) {
            visibleRows = i + 1;
        } else {
            break;
        }
    }

    // 隐藏超出行
    for (let i = 0; i < rows.length; i++) {
        rows[i].children.forEach(child => { child.style.display = i < visibleRows ? '' : 'none'; });
    }

    // maxHeight 精确到最后可见行底边
    if (visibleRows > 0) {
        container.style.maxHeight = Math.ceil(rows[visibleRows - 1].bottom) + 'px';
    } else {
        container.style.maxHeight = '0';
    }
    container.style.overflow = 'hidden';
}

/**
 * IntersectionObserver 懒加载 — widget 进入视口时才执行 fetchFn
 * @param {string} widgetId - data-id
 * @param {Function} fetchFn - 要执行的加载函数
 */
function lazyLoadWidget(widgetId, fetchFn) {
    const el = document.querySelector(`.widget-item[data-id="${widgetId}"]`);
    if (!el) { fetchFn(); return; }
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
            observer.disconnect();
            fetchFn();
        }
    }, { rootMargin: '600px' });
    observer.observe(el);
}

window.fetchJSON = fetchJSON;
window.clearApiCache = clearApiCache;
window.fetchAndRender = fetchAndRender;
window.escapeHtml = escapeHtml;
window.safeText = safeText;
window.fitGridContent = fitGridContent;
window.lazyLoadWidget = lazyLoadWidget;
window.getDashboardSignal = getDashboardSignal;
