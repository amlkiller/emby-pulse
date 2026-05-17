/**
 * dashboard/state.js
 * 统一的仪表盘状态管理 — 封装 localStorage + 服务端同步
 * 🔥 支持跨设备同步布局
 */
const EP_STORAGE_KEY = 'ep_dashboard_state';

const DashboardState = {
    _state: null,
    _saveTimer: null,
    _serverLoaded: false,  // 🔥 标记服务端数据是否已加载

    /** 默认 widget 顺序 */
    defaultOrder: [
        'widget-weather', 'widget-sysmon', 'widget-added-stats', 'widget-storage',
        'widget-stats', 'widget-library', 'widget-latest', 'widget-recent-play',
        'widget-trend', 'widget-top-users', 'widget-calendar', 'widget-quality',
        'widget-clients', 'widget-connectivity', 'widget-tasks'
    ],

    /** Widget 中文名映射 */
    widgetNames: {
        'widget-weather': '当地天气', 'widget-sysmon': '服务器监控', 'widget-added-stats': '入库汇总',
        'widget-storage': '媒体库储量', 'widget-stats': '核心运营指标', 'widget-library': '我的媒体库',
        'widget-latest': '最近入库媒体', 'widget-recent-play': '全站最近播放', 'widget-trend': '趋势追踪',
        'widget-top-users': '白金观影榜', 'widget-calendar': '今日追剧日历', 'widget-quality': '媒体库质量',
        'widget-clients': '终端分布', 'widget-connectivity': '外部服务', 'widget-tasks': '后台任务'
    },

    /** 从服务端 / localStorage 加载状态 - 🔥 优先服务端，localStorage 作为快速回退 */
    async load() {
        // 🔥 先从 localStorage 快速加载（秒出）
        let saved = null;
        const raw = localStorage.getItem(EP_STORAGE_KEY);
        if (raw) try { saved = JSON.parse(raw); } catch (_) {}

        const defaultSizes = {};
        document.querySelectorAll('.widget-item[data-id]').forEach(el => {
            defaultSizes[el.dataset.id] = el.dataset.defaultSize || '1x1';
        });

        if (!saved) {
            saved = { order: [...this.defaultOrder], visible: {}, sizes: { ...defaultSizes } };
            this.defaultOrder.forEach(id => saved.visible[id] = true);
        }
        if (!saved.sizes) saved.sizes = { ...defaultSizes };

        // 补全新增 widget + 兼容旧格式
        const oldToNew = { '1x1': null, '2x1': null, '3x1': null, '4x1': null, '1x2': null, '2x2': null, '3x2': null, '4x2': null };
        this.defaultOrder.forEach(id => {
            if (saved.sizes[id] === undefined) saved.sizes[id] = defaultSizes[id] || '1x3';
            if (typeof saved.sizes[id] === 'number') saved.sizes[id] = saved.sizes[id] + 'x3';
            const s = String(saved.sizes[id]);
            if (s in oldToNew) {
                const [ow, oh] = s.split('x').map(Number);
                saved.sizes[id] = `${ow}x${oh <= 2 ? oh * 3 : oh}`;
            }
            if (!saved.order.includes(id)) { saved.order.push(id); saved.visible[id] = true; }
            if (saved.visible[id] === undefined) saved.visible[id] = true;
        });

        this._state = saved;
        
        // 🔥 服务端同步（优先使用服务端数据）
        try {
            const res = await fetch('/api/dashboard/layout');
            const json = await res.json();
            if (json.status === 'success' && json.data) {
                // 🔥 服务端数据优先，合并到本地
                this._state = { ...saved, ...json.data };
                this._serverLoaded = true;
                // 更新 localStorage
                localStorage.setItem(EP_STORAGE_KEY, JSON.stringify(this._state));
                console.log('[Dashboard] 已从服务端同步布局');
            }
        } catch (e) {
            console.log('[Dashboard] 服务端布局同步失败，使用本地缓存');
        }

        return this._state;
    },

    /** 获取当前状态（只读快照） */
    get() {
        return this._state;
    },

    /** 更新状态字段并自动持久化（防抖 300ms） */
    update(patch) {
        Object.assign(this._state, patch);
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => this._persist(), 300);
    },

    /** 更新单个 widget 的可见性 */
    setVisible(id, visible) {
        this._state.visible[id] = visible;
        this._persist();
    },

    /** 更新单个 widget 的尺寸 */
    setSize(id, size) {
        this._state.sizes[id] = size;
        this._persist();
    },

    /** 更新排序 */
    setOrder(order) {
        this._state.order = order;
        this._persist();
    },

    /** 重置为默认 */
    reset() {
        localStorage.removeItem(EP_STORAGE_KEY);
        // 🔥 同时清除服务端布局
        fetch('/api/dashboard/layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        }).catch(() => {});
        this._state = null;
    },

    /** 内部：写 localStorage + 同步服务端 */
    _persist() {
        localStorage.setItem(EP_STORAGE_KEY, JSON.stringify(this._state));
        // 🔥 同步到服务端（跨设备同步）
        fetch('/api/dashboard/layout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this._state)
        }).then(() => {
            console.log('[Dashboard] 布局已同步到服务端');
        }).catch(() => {});
    }
};

window.DashboardState = DashboardState;
