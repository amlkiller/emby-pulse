/**
 * dashboard/layout.js
 * 网格布局引擎 — 响应式列数，60px 行粒度，底边竖向 resize
 */
const Layout = (() => {
    const ROW_H = 60;  // grid-auto-rows: 60px
    const GAP = 20;    // gap-5 = 20px

    /** 根据屏幕宽度计算列数 */
    function getCols() {
        const w = window.innerWidth;
        if (w < 768) return 1;      // 移动端
        if (w < 1024) return 2;     // 小笔记本
        if (w < 1366) return 3;     // 中等屏幕
        return 4;                    // 大屏幕
    }

    function parseSizeStr(sizeStr) {
        if (typeof sizeStr === 'number') return { w: sizeStr, h: 3 };
        const parts = String(sizeStr).split('x');
        return { w: Math.min(parseInt(parts[0]) || 1, getCols()), h: parseInt(parts[1]) || 3 };
    }

    function applyWidgetSize(el, sizeStr) {
        const cols = getCols();
        const { w, h } = parseSizeStr(sizeStr);
        // 确保宽度不超过当前列数
        const actualW = Math.min(w, cols);
        
        if (window.innerWidth >= 768) {
            el.style.gridColumn = `span ${actualW}`;
            el.style.gridRow = `span ${h}`;
            el.style.minHeight = '0';
            el.style.height = '';
        } else {
            el.style.gridColumn = '';
            el.style.gridRow = '';
            el.style.minHeight = '';
            el.style.height = '';
        }
    }

    /** 底边拖拽 resize — 只调整高度（行数），宽度在 manager 里改 */
    function startResize(e, el) {
        e.preventDefault();
        e.stopPropagation();

        const id = el.dataset.id;
        const startY = e.clientY;
        const startRect = el.getBoundingClientRect();
        const state = DashboardState.get();
        const { w } = parseSizeStr(state.sizes[id] || el.dataset.defaultSize || '1x3');

        // 创建遮罩层防止 iframe 等元素干扰，同时拦截所有鼠标事件
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;cursor:ns-resize;background:transparent;';
        document.body.appendChild(overlay);

        // 创建尺寸提示徽章
        const badge = document.createElement('div');
        badge.style.cssText = 'position:fixed;padding:4px 10px;background:rgba(0,122,255,0.9);color:#fff;font-size:12px;font-weight:700;border-radius:8px;pointer-events:none;z-index:10000;font-family:ui-monospace,monospace;box-shadow:0 2px 8px rgba(0,0,0,0.2);';
        document.body.appendChild(badge);

        let newH = parseSizeStr(state.sizes[id] || el.dataset.defaultSize || '1x3').h;

        const onMove = (ev) => {
            const deltaY = ev.clientY - startY;
            const totalH = startRect.height + deltaY;
            newH = Math.max(2, Math.round((totalH + GAP / 2) / (ROW_H + GAP)));
            badge.textContent = `${w}x${newH}`;
            badge.style.left = (ev.clientX + 12) + 'px';
            badge.style.top = (ev.clientY - 20) + 'px';
            // 实时预览高度
            el.style.gridRow = `span ${newH}`;
            el.style.outline = '2px solid #007AFF';
            el.style.outlineOffset = '-2px';
        };

        const onUp = () => {
            overlay.removeEventListener('mousemove', onMove);
            overlay.removeEventListener('mouseup', onUp);
            overlay.remove();
            badge.remove();
            el.style.outline = '';
            el.style.outlineOffset = '';
            setWidgetSize(id, `${w}x${newH}`);
        };

        // 在 overlay 上监听鼠标事件（工作版本的方式）
        overlay.addEventListener('mousemove', onMove);
        overlay.addEventListener('mouseup', onUp);
    }

    /** 初始化布局 */
    async function init() {
        const grid = document.getElementById('dashboard-grid');
        const state = await DashboardState.load();
        const elements = Array.from(grid.children);

        // 按保存的顺序排列 DOM
        state.order.forEach(id => {
            const el = elements.find(e => e.dataset.id === id);
            if (el) grid.appendChild(el);
        });

        // 应用可见性和尺寸
        elements.forEach(el => {
            const id = el.dataset.id;
            if (state.visible[id] === false) el.classList.add('hidden');
            else el.classList.remove('hidden');
            applyWidgetSize(el, state.sizes[id] || el.dataset.defaultSize || '1x3');
        });

        // 注入底边 resize 手柄
        elements.forEach(el => {
            if (!el.querySelector('.widget-resize-handle')) {
                const handle = document.createElement('div');
                handle.className = 'widget-resize-handle';
                el.style.position = 'relative';
                el.appendChild(handle);
                // 直接绑定 mousedown 事件
                handle.addEventListener('mousedown', (e) => startResize(e, el));
            }
        });

        // 🔥 拖拽排序：使用拖拽手柄，避免影响内部按钮点击
        if (typeof Sortable !== 'undefined') {
            new Sortable(grid, {
                animation: 300,
                ghostClass: 'sortable-ghost',
                dragClass: 'sortable-drag',
                easing: 'cubic-bezier(1, 0, 0, 1)',
                forceFallback: true,
                scrollSensitivity: 100,
                scrollSpeed: 20,
                bubbleScroll: true,
                handle: '.widget-drag-handle',
                filter: '.widget-menu-btn, button, input, select, a, canvas',
                preventOnFilter: false,
                onEnd() {
                    const order = Array.from(grid.children).map(el => el.dataset.id);
                    DashboardState.setOrder(order);
                }
            });
        } else {
            console.warn('SortableJS not loaded');
        }
    }

    /** 内容自适应 */
    function applyContentFit() {
        fitGridContent('latest-container');
        fitGridContent('recent-container');
        fitGridContent('library-container');
    }

    /** 全局 resize 监听 */
    let _resizeTimer = null;
    function setupResizeObserver() {
        new ResizeObserver(() => {
            clearTimeout(_resizeTimer);
            _resizeTimer = setTimeout(() => {
                const state = DashboardState.get();
                if (state) {
                    document.querySelectorAll('.widget-item[data-id]').forEach(el => {
                        applyWidgetSize(el, state.sizes[el.dataset.id] || el.dataset.defaultSize || '1x3');
                    });
                }
                applyContentFit();
                if (window._trendChart) window._trendChart.resize();
                if (window._addedStatsChart) window._addedStatsChart.resize();
            }, 150);
        }).observe(document.body);
    }

    return { init, applyWidgetSize, applyContentFit, setupResizeObserver, parseSizeStr, getCols, ROW_H, GAP };
})();

/** 全局函数：设置 widget 尺寸 */
function setWidgetSize(id, size) {
    const el = document.querySelector(`.widget-item[data-id="${id}"]`);
    if (el) Layout.applyWidgetSize(el, size);
    DashboardState.setSize(id, size);

    // 更新 manager modal 中的宽度按钮高亮
    const row = document.getElementById(`width-row-${id}`);
    if (row) {
        const { w } = Layout.parseSizeStr(size);
        row.querySelectorAll('button').forEach(btn => {
            const btnW = parseInt(btn.dataset.w);
            const active = btnW === w;
            btn.className = 'px-3 py-1 rounded-lg text-[12px] font-bold transition-all '
                + (active ? 'bg-brand-500 text-white shadow-sm' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700');
        });
    }

    if (id === 'widget-trend' && window._trendChart) setTimeout(() => window._trendChart.resize(), 350);
    if (id === 'widget-added-stats' && window._addedStatsChart) setTimeout(() => window._addedStatsChart.resize(), 350);
    setTimeout(Layout.applyContentFit, 100);
}

window.Layout = Layout;
window.setWidgetSize = setWidgetSize;
