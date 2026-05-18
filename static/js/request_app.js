/* ============================================================
   EmbyPulse 玩家社区 - 核心逻辑驱动 (高容错稳定版 + 全选修复)
   ============================================================ */
async function toBase64(url) { try { const res = await fetch(url); if (!res.ok) throw new Error(`HTTP ${res.status}`); const blob = await res.blob(); return new Promise((resolve) => { const reader = new FileReader(); reader.onloadend = () => resolve(reader.result); reader.readAsDataURL(blob); }); } catch (e) { return null; } }
async function applyPhysicalBlur(base64Url) { return new Promise((resolve) => { const img = new Image(); img.onload = () => { const canvas = document.createElement('canvas'); const ctx = canvas.getContext('2d'); canvas.width = 400; canvas.height = 800; ctx.filter = 'blur(40px) brightness(0.4)'; const scale = Math.max(canvas.width / img.width, canvas.height / img.height); ctx.drawImage(img, (canvas.width / 2) - (img.width / 2) * scale, (canvas.height / 2) - (img.height / 2) * scale, img.width * scale, img.height * scale); resolve(canvas.toDataURL('image/jpeg', 0.8)); }; img.onerror = () => resolve(base64Url); img.src = base64Url; }); }
window.tmdbCache = {};
window.fallbackPoster = async function(img, title) { if (img.getAttribute('data-fallback-done')) return; img.setAttribute('data-fallback-done', 'true'); img.src = '/static/img/logo-app-2.png'; img.classList.add('opacity-30', 'object-contain', 'p-4'); if (!title || title === 'undefined' || title === 'null') return; try { const res = await fetch(`/api/requests/search?query=${encodeURIComponent(title)}`); const data = await res.json(); if (data.status === 'success' && data.data.length > 0) { const match = data.data.find(d => d.poster_path) || data.data[0]; if (match.poster_path) { img.src = match.poster_path; img.classList.remove('opacity-30', 'object-contain', 'p-4'); img.classList.add('object-cover'); } } } catch(e) {} };
window.fallbackReportPoster = async function(imgEl, title) { if(imgEl.getAttribute('data-fallback-done')) return; imgEl.setAttribute('data-fallback-done', 'true'); imgEl.src = '/static/img/logo-app-2.png'; imgEl.classList.add('poster-fallback'); try { const res = await fetch(`/api/requests/search?query=${encodeURIComponent(title)}`); const data = await res.json(); if (data.status === 'success' && data.data.length > 0) { const match = data.data.find(d => d.poster_path) || data.data[0]; if (match.poster_path) { const b64 = await toBase64(match.poster_path); if(b64) { imgEl.src = b64; imgEl.classList.remove('poster-fallback'); imgEl.style.objectFit = "cover"; } } } } catch(e) {} };

// 🔥 处理封面 URL：优先 TMDB 公网 URL，内网地址转为代理 URL
window.getSafePosterUrl = function(item) {
    if (!item || !item.Id) return '/static/img/logo-app-2.png';
    
    const poster = item.Poster || '';
    // 如果 Poster 是 TMDB 公网 URL，直接返回
    if (poster && poster.includes('image.tmdb.org')) {
        return poster;
    }
    // 如果 Poster 是 Emby 内网地址，转换为代理 URL
    if (poster && (poster.includes('/emby/Items/') || poster.includes('&api_key='))) {
        return `/api/proxy/smart_image?item_id=${item.Id}&type=Primary`;
    }
    // 如果 Poster 为空，使用代理 API
    if (!poster) {
        return `/api/proxy/smart_image?item_id=${item.Id}&type=Primary`;
    }
    return poster;
};

document.addEventListener('alpine:init', () => {
    Alpine.data('dragScroll', () => ({ isDown: false, isDragging: false, startX: 0, scrollLeft: 0, start(e) { this.isDown = true; this.isDragging = false; this.startX = e.pageX - this.$el.offsetLeft; this.scrollLeft = this.$el.scrollLeft; }, end() { this.isDown = false; setTimeout(() => { this.isDragging = false; }, 50); }, move(e) { if (!this.isDown) return; this.isDragging = true; e.preventDefault(); const walk = (e.pageX - this.$el.offsetLeft - this.startX) * 1.5; this.$el.scrollLeft = this.scrollLeft - walk; } }));

    Alpine.data('requestApp', () => ({
        scrolled: false, lastScrollTop: 0, isScrollingDown: false, isLoaded: false, isLoggedIn: false, isDarkMode: false,
        userId: '', userName: '', expireDate: '未知', serverUrl: '', showServerUrl: false, 
        loginMode: 'login', // 🔥 登录/注册模式切换
        loginForm: { username: '', password: '' }, isLoggingIn: false, showLoginPassword: false,
        registerForm: { code: '', username: '', password: '' }, isRegistering: false, showRegisterPassword: false, // 🔥 注册表单 + 密码显示
        welcomeModal: { show: false, message: '', expireText: '', password: '' }, showWelcomePassword: false, // 🔥 欢迎弹窗 + 密码显示
        currentTab: 'explore', searchQuery: '', isSearching: false, searchResults: [], recommendResults: [], recommendRow1: [], recommendRow2: [], recommendRow3: [],
        serverDashboard: null, serverLatest: [], serverTopRated: [], serverGenres: [], serverTopMovies: [], serverTopSeries: [],
        showcaseModal: { open: false, isLoading: false, data: null }, queueModal: { open: false, activeTab: 'request' }, myQueue: [], myFeedbacks: [],
        userStats: null, userBadges: [], userTrend: null, isStatsLoading: false, statsLoaded: false, charts: { hour: null, device: null, client: null, trend: null },
        isModalOpen: false, activeItem: null, tvSeasons: [], isLoadingSeasons: false, isCheckingLocal: false, selectedSeasons: [], isSubmitting: false,
        toast: { show: false, message: '', type: 'success' }, feedbackModal: { open: false, itemName: '', posterPath: '', issueType: '缺少字幕', desc: '' }, feedbackIssues: ['缺少字幕', '字幕错位', '视频卡顿/花屏', '清晰度太低', '音轨无声/音画不同步', '其他问题'], isFeedbackSubmitting: false,
        posterStudio: { open: false, isLoading: false, isSaving: false, period: 'month', periodLabel: '本月 观影报告', data: null, useCoverBg: false, top1BgBase64: null },
        msgModalOpen: false, userMessages: [], userUnreadCount: 0, userNewMessage: '', userSending: false, showEmojiPicker: false, userMuteInfo: null,
        
        // 🔥 积分引擎相关变量
        points: 0, isLoadingPoints: false, hasCheckedIn: false, isCheckingIn: false,
        
        // 🔥 PWA 图标相关变量
        iconModalOpen: false, iconsLoading: false, availableIcons: [], currentIcon: 'default',
        checkinReward: 0, showRewardBubble: false, rewardBubbleTimer: null,
        storeModalOpen: false, showMyLogs: false, myLogs: [], config: {},
        logsPage: 1, logsPageSize: 20, logsTotal: 0, logsTotalPages: 0, logsLoading: false,
        redeemResult: { show: false, type: '', title: '', message: '' },
        isRedeeming: false, // 🔥 兑换进行中状态
        
        // 🔥 求片积分配置
        requestCostConfig: { enabled: false, cost: 0, mode: 'per_request' },
        
        // 🔥 用户求片权限
        reqFree: 0,  // 0=跟随全局, 1=免费
        reqFreeCount: -1,  // -1=无限次, >=0=剩余次数
        
        // 公告相关
        announcements: [],
        announcementDetail: { show: false, data: null, index: 0 },
        announcementScrollInterval: null,
        currentAnnouncementIndex: 0,

        // 🔥 下拉刷新状态
        pullState: { startY: 0, pulling: false, threshold: 60 },
        
        // 🔥 加载登录背景海报
        async loadLoginBackground() {
            try {
                const res = await fetch('/api/wallpaper');
                const data = await res.json();
                if (data.status === 'success' && data.url) {
                    // 预加载图片
                    const img = new Image();
                    img.src = data.url;
                    img.onload = () => {
                        const el = document.getElementById('login-bg-poster');
                        if (el) {
                            el.style.backgroundImage = `url('${data.url}')`;
                            el.classList.remove('opacity-0', 'scale-[1.02]');
                            el.classList.add('opacity-100', 'scale-100');
                        }
                    };
                }
            } catch(e) {
                console.log('加载背景失败:', e);
            }
        },
        
        handlePullStart(e) {
            if (window.scrollY === 0) {
                this.pullState.startY = e.touches[0].clientY;
                this.pullState.pulling = true;
            }
        },
        
        handlePullMove(e) {
            if (!this.pullState.pulling || !this.isLoggedIn) return;
            const currentY = e.touches[0].clientY;
            const diff = currentY - this.pullState.startY;
            
            if (diff > 0 && window.scrollY === 0) {
                // 阻止原生下拉刷新
                e.preventDefault();
                
                const indicator = document.getElementById('pull-indicator');
                const icon = document.getElementById('pull-icon');
                const text = document.getElementById('pull-text');
                
                const progress = Math.min(diff / 150, 1);
                indicator.style.transform = `translateY(${Math.min(diff * 0.4, 50) - 50}px)`;
                
                if (diff >= this.pullState.threshold) {
                    indicator.classList.add('visible');
                    icon.className = 'fa-solid fa-arrow-up text-brand-500';
                    text.textContent = '释放刷新';
                } else {
                    indicator.classList.add('visible');
                    icon.className = 'fa-solid fa-arrow-down text-brand-500';
                    text.textContent = '下拉刷新';
                }
            }
        },
        
        async handlePullEnd(e) {
            if (!this.pullState.pulling) return;
            this.pullState.pulling = false;
            
            const indicator = document.getElementById('pull-indicator');
            const icon = document.getElementById('pull-icon');
            const text = document.getElementById('pull-text');
            
            const currentY = e.changedTouches[0].clientY;
            const diff = currentY - this.pullState.startY;
            
            if (diff >= this.pullState.threshold && this.isLoggedIn) {
                // 触发刷新
                indicator.classList.add('refreshing');
                icon.className = 'fa-solid fa-spinner fa-spin text-brand-500';
                text.textContent = '刷新中...';
                
                await this.doRefresh();
                
                indicator.classList.remove('refreshing', 'visible');
                indicator.style.transform = 'translateY(-50px)';
            } else {
                indicator.classList.remove('visible');
                indicator.style.transform = 'translateY(-50px)';
            }
        },

        async doRefresh() { 
            // 🔥 局部刷新：只刷新当前 tab 的内容，不重置页面
            this.showToast('刷新中...', 'success'); 
            
            // 刷新服务器数据
            await this.loadServerData();
            
            // 刷新当前 tab 的特定内容
            if (this.currentTab === 'profile') {
                this.statsLoaded = false;
                await this.loadProfileStats();
            } else if (this.currentTab === 'explore') {
                // 重新加载公告
                await this.loadAnnouncements();
            }
            
            this.showToast('刷新完成', 'success');
        },

        async initTheme() { 
            this.isDarkMode = document.documentElement.classList.contains('dark'); 
            
            // 🔥 从 URL 参数恢复 tab 状态 + 检测邀请码（合并，避免重复声明）
            const urlParams = new URLSearchParams(window.location.search);
            
            // 恢复 tab 状态
            const tabParam = urlParams.get('tab');
            if (tabParam && ['explore', 'request', 'profile'].includes(tabParam)) {
                this.currentTab = tabParam;
            }
            
            // 检测邀请码，自动切换到注册模式
            const inviteCode = urlParams.get('code');
            if (inviteCode) {
                this.loginMode = 'register';
                this.registerForm.code = inviteCode;
            }
            
            // 🔥 加载求片积分配置
            this.loadRequestCostConfig();
            
            // 🔥 检查是否刚退出登录（防止自动重新登录）
            if (sessionStorage.getItem('user_logout_redirect')) {
                sessionStorage.removeItem('user_logout_redirect');
                this.isLoggedIn = false;
                this.isLoaded = true;
                return;
            }
            
            // 检查是否刚被登出（避免刷新死循环）
            if (sessionStorage.getItem('account_deleted_redirect')) {
                sessionStorage.removeItem('account_deleted_redirect');
                // 先清除服务端 session
                try {
                    await fetch('/api/requests/logout', { method: 'POST' });
                } catch(e) {}
                this.isLoggedIn = false;
                this.isLoaded = true;
                this.showToast('账号已被删除，请重新登录', 'error');
                return;
            }
            
            if (sessionStorage.getItem('account_disabled_redirect')) {
                sessionStorage.removeItem('account_disabled_redirect');
                try {
                    await fetch('/api/requests/logout', { method: 'POST' });
                } catch(e) {}
                this.isLoggedIn = false;
                this.isLoaded = true;
                this.showToast('您的账号已被禁用，如需启用请联系管理员', 'error');
                return;
            }
            
            try { 
                const res = await fetch('/api/requests/check'); 
                const data = await res.json(); 
                if (data.status === 'success') { 
                    this.isLoggedIn = true; 
                    this.userId = data.user.Id; 
                    this.userName = data.user.Name; 
                    this.expireDate = data.user.expire_date; 
                    this.serverUrl = data.server_url;
                    this.loadServerData(); 
                    this.loadUserMessages();
                    this.loadAnnouncements();
                    
                    // 🔥 根据恢复的 tab 状态加载对应数据
                    if (this.currentTab === 'profile') {
                        this.loadProfileStats();
                    }
                    
                    // 过期提示
                    if (data.user.expired) {
                        this.showToast('您的账号已过期，请及时续费', 'error');
                    }
                } else if (data.account_deleted) {
                    // 账号已被删除，设置标记并显示登录页
                    sessionStorage.setItem('account_deleted_redirect', 'true');
                    this.isLoggedIn = false;
                    this.isLoaded = true;
                    this.showToast('账号已被删除，请重新登录', 'error');
                    return;
                } else if (data.disabled) {
                    // 账号被封禁
                    sessionStorage.setItem('account_disabled_redirect', 'true');
                    this.isLoggedIn = false;
                    this.isLoaded = true;
                    this.showToast('您的账号已被禁用，如需启用请联系管理员', 'error');
                    return;
                }
            } catch(e) {} 
            this.isLoaded = true; 
        },
        handleScroll() { const st = window.pageYOffset || document.documentElement.scrollTop; this.scrolled = st > 50; this.isScrollingDown = st > this.lastScrollSt && st > 50; this.lastScrollSt = st <= 0 ? 0 : st; },
        toggleTheme() { this.isDarkMode = !this.isDarkMode; localStorage.setItem('ep_theme', this.isDarkMode ? 'dark' : 'light'); document.documentElement.classList.toggle('dark', this.isDarkMode); if (this.currentTab === 'profile' && this.statsLoaded) setTimeout(() => this.renderCharts(), 150); },
        showToast(msg, type = 'success') { this.toast = { show: true, message: msg, type }; setTimeout(() => this.toast.show = false, 3000); },
        async copyToClipboard(text) { try { await navigator.clipboard.writeText(text); } catch(e) { const input = document.createElement('input'); input.value = text; document.body.appendChild(input); input.select(); document.exec_command('copy'); document.body.removeChild(input); } },
        
        // 🔥 加载求片积分配置
        async loadRequestCostConfig() {
            try {
                const res = await fetch('/api/user/points/info');
                const data = await res.json();
                if (data.status === 'success') {
                    this.requestCostConfig.enabled = data.data.config.enable_req_cost === '1';
                    // 🔥 修复：使用 !== undefined 判断，允许值为 0
                    const costValue = parseInt(data.data.config.req_cost);
                    this.requestCostConfig.cost = !isNaN(costValue) ? costValue : 50;
                    this.requestCostConfig.mode = data.data.config.req_cost_mode || 'per_request';
                    // 🔥 用户求片权限
                    this.reqFree = data.data.req_free || 0;
                    this.reqFreeCount = data.data.req_free_count ?? -1;
                }
            } catch(e) {}
        },
        
        // 🔥 计算求片积分（实时）
        calculateRequestCost(seasonsCount, mediaType) {
            if (!this.requestCostConfig.enabled) return 0;
            if (this.requestCostConfig.mode === 'per_season' && mediaType === 'tv' && seasonsCount > 0) {
                return this.requestCostConfig.cost * seasonsCount;
            }
            return this.requestCostConfig.cost;
        },
        
        // 🔥 求片季数变化时重新计算积分（用于 modal_request_confirm.html）
        calculateCost() {
            // 这个函数不需要做任何事，因为 calculateRequestCost 是实时计算的
            // 但需要触发 Alpine.js 的响应式更新
            this.selectedSeasons = [...this.selectedSeasons];
        },
        
        // 🔥 我的追剧相关方法
        // 🔥 我的追剧相关方法和变量 - 多季选择优化版
        mySeries: [],
        mySeriesLoading: false,
        mySeriesModalOpen: false,
        selectedSeries: null,
        selectedEpisodesBySeason: {},  // 🔥 按季存储: {season: [episodes]}
        selectedEpisodes: [],  // 🔥 单季选择（兼容旧版本）
        selectedSeason: null,  // 🔥 当前选中的季
        submittingUpdate: false,
        updateCostInfo: { enabled: false, cost: 0, mode: 'per_series', base_cost: 0 },
        mySeriesCacheInfo: { exists: false, expired: false, updated_at: '', interval_hours: 6 },
        mySeriesRefreshing: false,
        
        // 🔥 媒体库设置相关
        libSettingsModalOpen: false,
        libSettingsLoading: false,
        libSettingsSaving: false,
        libList: [],
        libHiddenIds: [],  // 保存原始隐藏ID列表
        
        // 🔥 娱乐功能相关
        entertainmentModalOpen: false,
        
        // 🎰 老虎机相关
        slotGameOpen: false,
        slotEnabled: false,
        slotCost: 10,
        slotDailyFree: 3,
        slotMaxPerDay: 20,
        slotUsedToday: 0,
        slotDailyFreeLeft: 0,
        slotTripleMultiplier: 10,
        slotDoubleMultiplier: 2,
        slotSpecialMultiplier: 50,
        slotSymbols: [],
        slotReels: ['❓', '❓', '❓'],
        slotSpinning: false,
        slotResult: '',
        slotWin: false,
        slotWinAmount: 0,
        userPoints: 0,
        
        // 🎫 刮刮乐相关
        scratchGameOpen: false,
        scratchEnabled: false,
        scratchCost: 10,
        scratchWinNumbers: [],
        scratchGrid: [],
        scratchWinNumbersCount: 3,
        scratchGridCount: 12,
        scratchMinReward: 5,
        scratchMaxReward: 100,
        scratchMatchRate: 20,
        scratchTotalReward: 0,
        scratchBuying: false,
        
        // 🎡 转盘相关
        wheelGameOpen: false,
        wheelEnabled: false,
        wheelCost: 10,
        wheelDailyFree: 3,
        wheelMaxPerDay: 20,
        wheelUsedToday: 0,
        wheelDailyFreeLeft: 0,
        wheelSpinning: false,
        wheelResult: '',
        wheelReward: 0,
        wheelSectors: [],
        wheelRotation: 0,
        wheelBlinking: false,
        wheelWinIndex: -1,
        wheelWinReward: null,
        wheelAnimOffset: 0,
        wheelScrollList: [],
        wheelScrollOffset: 0,
        wheelLightIndex: -1,
        
        // 🎲 猜数字相关
        guessGameOpen: false,
        guessEnabled: false,
        guessCost: 5,
        guessRange: '1-100',
        guessMin: 1,
        guessMax: 100,
        guessMaxTries: 7,
        guessBaseReward: 50,
        guessMultipliers: [5, 3, 2, 1.5, 1.2, 1, 0.8],
        guessPlaying: false,
        guessTargetNumber: 0,
        guessTriesLeft: 7,
        guessHistory: [],
        guessInput: '',
        guessHint: '',
        guessResult: '',
        guessWon: false,
        guessReward: 0,
        guessSubmitting: false,
        
        // 🎟️ 彩票相关
        lotteryGameOpen: false,
        lotteryEnabled: false,
        lotteryCost: 100,
        lotteryMaxPerDay: 10,
        lotteryDrawHour: 20,
        lotteryPool: 0,
        lotteryTodayTickets: 0,
        lotteryMyTickets: [],
        lotteryBuyCount: 1,
        lotteryBuying: false,
        lotteryAutoPick: true,
        lotteryCustomNumber: ['', '', '', ''],
        lotteryTodayResult: null,
        lotteryHistory: [],
        lotteryShowHistory: false,
        lotteryNextDrawTime: '',
        lotteryIsDrawn: false,
        lotteryMyWinning: [],
        lotteryMyPrizeTotal: 0,
        
        // 加载老虎机配置
        async loadSlotConfig() {
            try {
                const res = await fetch('/api/points/config');
                const json = await res.json();
                if (json.status === 'success') {
                    const d = json.data;
                    this.slotEnabled = d.enable_slot === '1';
                    this.slotCost = parseInt(d.slot_cost) || 10;
                    this.slotDailyFree = d.slot_daily_free !== undefined ? parseInt(d.slot_daily_free) : 3;
                    this.slotMaxPerDay = parseInt(d.slot_max_per_day) || 20;
                    this.slotTripleMultiplier = parseInt(d.slot_triple_multiplier) || 10;
                    this.slotDoubleMultiplier = parseInt(d.slot_double_multiplier) || 2;
                    this.slotSpecialMultiplier = parseInt(d.slot_special_multiplier) || 50;
                    
                    // 解析图案配置
                    try {
                        const symbolsText = d.slot_symbols || '🍒|20|false\n🍋|20|false\n🍊|15|false\n🍇|15|false\n💎|10|false\n7️⃣|10|true\n⭐|5|true\n🎰|5|true';
                        this.slotSymbols = symbolsText.split('\n').filter(s => s.trim()).map(line => {
                            const [emoji, weight, special] = line.split('|');
                            return { emoji: emoji.trim(), weight: parseInt(weight) || 10, special: special === 'true' };
                        });
                    } catch (e) {
                        this.slotSymbols = [
                            { emoji: '🍒', weight: 20, special: false },
                            { emoji: '🍋', weight: 20, special: false },
                            { emoji: '🍊', weight: 15, special: false },
                            { emoji: '🍇', weight: 15, special: false },
                            { emoji: '💎', weight: 10, special: false },
                            { emoji: '7️⃣', weight: 10, special: true },
                            { emoji: '⭐', weight: 5, special: true },
                            { emoji: '🎰', weight: 5, special: true }
                        ];
                    }
                    
                    // 加载今日使用次数
                    await this.loadSlotUsage();
                }
            } catch (e) {
                console.error('加载老虎机配置失败', e);
            }
        },
        
        // 加载今日使用次数
        async loadSlotUsage() {
            try {
                const res = await fetch('/api/slot/usage');
                const json = await res.json();
                if (json.status === 'success') {
                    this.slotUsedToday = json.used_today || 0;
                    this.slotDailyFreeLeft = Math.max(0, this.slotDailyFree - this.slotUsedToday);
                }
            } catch (e) {
                console.error('加载老虎机使用次数失败', e);
            }
        },
        
        // 打开老虎机游戏
        openSlotGame() {
            if (!this.slotEnabled) {
                this.showToast('老虎机功能未启用', 'error');
                return;
            }
            this.slotGameOpen = true;
            this.slotResult = '';
            this.slotWin = false;
            this.slotWinAmount = 0;
            this.slotReels = ['❓', '❓', '❓'];
        },
        
        // 随机选择图案（按权重）
        getRandomSymbol() {
            const totalWeight = this.slotSymbols.reduce((sum, s) => sum + s.weight, 0);
            let random = Math.random() * totalWeight;
            for (const symbol of this.slotSymbols) {
                random -= symbol.weight;
                if (random <= 0) return symbol;
            }
            return this.slotSymbols[0];
        },
        
        // 旋转老虎机
        async spinSlot() {
            if (this.slotSpinning) return;
            
            // 检查积分
            const isFree = this.slotDailyFreeLeft > 0;
            if (!isFree && this.userPoints < this.slotCost) {
                this.showToast('积分不足', 'error');
                return;
            }
            
            this.slotSpinning = true;
            this.slotResult = '';
            this.slotWin = false;
            this.slotWinAmount = 0;
            
            // 调用后端 API
            try {
                const res = await fetch('/api/slot/spin', { method: 'POST' });
                const json = await res.json();
                
                if (json.status === 'success') {
                    // 动画效果：快速切换图案
                    const animDuration = 2000;
                    const animInterval = 100;
                    const animSteps = animDuration / animInterval;
                    let step = 0;
                    
                    const animTimer = setInterval(() => {
                        this.slotReels = [
                            this.getRandomSymbol().emoji,
                            this.getRandomSymbol().emoji,
                            this.getRandomSymbol().emoji
                        ];
                        step++;
                        if (step >= animSteps) {
                            clearInterval(animTimer);
                            // 显示最终结果
                            this.slotReels = json.result;
                            this.slotWin = json.win;
                            this.slotWinAmount = json.reward || 0;
                            this.slotResult = json.message;
                            this.slotSpinning = false;
                            
                            // 更新积分和使用次数
                            this.userPoints = json.new_points || this.userPoints;
                            this.slotUsedToday = json.used_today || this.slotUsedToday;
                            this.slotDailyFreeLeft = Math.max(0, this.slotDailyFree - this.slotUsedToday);
                            
                            if (this.slotWin) {
                                this.showToast(`恭喜获得 ${this.slotWinAmount} 积分！`, 'success');
                            }
                        }
                    }, animInterval);
                } else {
                    this.slotSpinning = false;
                    this.showToast(json.message || '抽奖失败', 'error');
                }
            } catch (e) {
                this.slotSpinning = false;
                this.showToast('网络错误', 'error');
            }
        },
        
        // 🎫 刮刮乐方法
        async loadScratchConfig() {
            try {
                const res = await fetch('/api/points/config');
                const json = await res.json();
                if (json.status === 'success') {
                    const d = json.data;
                    this.scratchEnabled = d.enable_web_scratch === '1';
                    this.scratchCost = parseInt(d.web_scratch_cost) || 10;
                    this.scratchWinNumbersCount = parseInt(d.web_scratch_win_numbers) || 3;
                    this.scratchGridCount = parseInt(d.web_scratch_grid_count) || 12;
                    this.scratchMinReward = parseInt(d.web_scratch_min_reward) || 5;
                    this.scratchMaxReward = parseInt(d.web_scratch_max_reward) || 100;
                    this.scratchMatchRate = parseFloat(d.web_scratch_match_rate) || 20;
                }
            } catch (e) {
                console.error('加载刮刮乐配置失败', e);
            }
        },
        
        openScratchGame() {
            if (!this.scratchEnabled) {
                this.showToast('刮刮乐功能未启用', 'error');
                return;
            }
            this.scratchGameOpen = true;
            this.scratchGrid = [];
            this.scratchWinNumbers = [];
            this.scratchTotalReward = 0;
        },
        
        async buyNewCard() {
            if (this.scratchBuying) return;
            
            if (this.userPoints < this.scratchCost) {
                this.showToast('积分不足', 'error');
                return;
            }
            
            this.scratchBuying = true;
            
            try {
                const res = await fetch('/api/scratch/buy', { method: 'POST' });
                const json = await res.json();
                
                if (json.status === 'success') {
                    this.scratchWinNumbers = json.win_numbers || [];
                    this.scratchGrid = json.grid || [];
                    this.scratchTotalReward = 0;
                    this.userPoints = json.new_points || this.userPoints;
                    this.scratchBuying = false;
                    this.showToast('购买成功，开始刮卡吧！', 'success');
                } else {
                    this.scratchBuying = false;
                    this.showToast(json.message || '购买失败', 'error');
                }
            } catch (e) {
                this.scratchBuying = false;
                this.showToast('网络错误', 'error');
            }
        },
        
        async revealCell(index) {
            if (this.scratchGrid.length === 0) {
                this.showToast('请先购买刮刮卡', 'error');
                return;
            }
            
            const cell = this.scratchGrid[index];
            if (cell.revealed) return;
            
            try {
                const res = await fetch('/api/scratch/reveal', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cell_index: index })
                });
                const json = await res.json();
                
                if (json.status === 'success') {
                    this.scratchGrid[index] = {
                        ...this.scratchGrid[index],
                        revealed: true,
                        number: json.number,
                        reward: json.reward || 0,
                        matched: json.matched || false
                    };
                    
                    if (json.matched && json.reward > 0) {
                        this.scratchTotalReward += json.reward || 0;
                        this.userPoints = json.new_points || this.userPoints;
                        this.showToast(`🎉 匹配成功！+${json.reward} 积分！`, 'success');
                    }
                    
                    const allRevealed = this.scratchGrid.every(c => c.revealed);
                    if (allRevealed) {
                        setTimeout(() => {
                            if (this.scratchTotalReward > 0) {
                                this.showToast(`🎊 本卡共获得 ${this.scratchTotalReward} 积分！`, 'success');
                            } else {
                                this.showToast('很遗憾，本卡未中奖，再接再厉！', 'info');
                            }
                        }, 500);
                    }
                } else {
                    this.showToast(json.message || '刮开失败', 'error');
                }
            } catch (e) {
                this.showToast('网络错误', 'error');
            }
        },
        
        // 🎡 转盘方法
        async loadWheelConfig() {
            try {
                const res = await fetch('/api/points/config');
                const json = await res.json();
                if (json.status === 'success') {
                    const d = json.data;
                    this.wheelEnabled = d.enable_wheel === '1';
                    this.wheelCost = parseInt(d.wheel_cost) || 10;
                    this.wheelDailyFree = d.wheel_daily_free !== undefined ? parseInt(d.wheel_daily_free) : 3;
                    this.wheelMaxPerDay = parseInt(d.wheel_max_per_day) || 20;
                    
                    // 加载扇区配置
                    this.wheelSectors = [];
                    for (let i = 1; i <= 6; i++) {
                        this.wheelSectors.push({
                            reward: parseInt(d[`wheel_reward_${i}`]) || [50, 30, 20, 10, 5, 0][i-1],
                            weight: parseInt(d[`wheel_weight_${i}`]) || [5, 10, 15, 20, 25, 25][i-1]
                        });
                    }
                    
                    await this.loadWheelUsage();
                }
            } catch (e) {
                console.error('加载转盘配置失败', e);
            }
        },
        
        async loadWheelUsage() {
            try {
                const res = await fetch('/api/wheel/usage');
                const json = await res.json();
                if (json.status === 'success') {
                    this.wheelUsedToday = json.used_today || 0;
                    this.wheelDailyFreeLeft = Math.max(0, this.wheelDailyFree - this.wheelUsedToday);
                }
            } catch (e) {
                console.error('加载转盘使用次数失败', e);
            }
        },
        
        openWheelGame() {
            if (!this.wheelEnabled) {
                this.showToast('转盘功能未启用', 'error');
                return;
            }
            this.wheelGameOpen = true;
            this.wheelResult = '';
            this.wheelReward = 0;
        },
        
        async spinWheel() {
            if (this.wheelSpinning) return;
            
            const isFree = this.wheelDailyFreeLeft > 0;
            if (!isFree && this.userPoints < this.wheelCost) {
                this.showToast('积分不足', 'error');
                return;
            }
            
            this.wheelSpinning = true;
            this.wheelWinReward = null;
            this.wheelWinIndex = -1;
            this.wheelLightIndex = 0;
            
            try {
                const res = await fetch('/api/wheel/spin', { method: 'POST' });
                const json = await res.json();
                
                if (json.status === 'success') {
                    // 使用后端返回的扇区配置
                    if (json.sectors && json.sectors.length > 0) {
                        this.wheelSectors = json.sectors;
                    }
                    
                    const winIndex = json.sector_index;
                    
                    // 灯光循环转动动画
                    // 先快速转几圈，然后慢慢减速停在中奖位置
                    const totalSteps = 20; // 总共转20步
                    let currentStep = 0;
                    let speed = 50; // 初始速度50ms
                    
                    // 灯光转动
                    const lightInterval = setInterval(() => {
                        this.wheelLightIndex = currentStep % 6;
                        currentStep++;
                        
                        // 逐渐减速
                        if (currentStep > 15) {
                            speed = 100;
                        } else if (currentStep > 18) {
                            speed = 200;
                        }
                        
                        // 最后停在中奖位置
                        if (currentStep >= totalSteps) {
                            clearInterval(lightInterval);
                            this.wheelLightIndex = winIndex;
                            
                            // 显示结果
                            setTimeout(() => {
                                this.wheelWinIndex = winIndex;
                                this.wheelWinReward = json.reward;
                                this.wheelSpinning = false;
                                
                                this.userPoints = json.new_points || this.userPoints;
                                this.wheelUsedToday = json.used_today || this.wheelUsedToday;
                                this.wheelDailyFreeLeft = Math.max(0, this.wheelDailyFree - this.wheelUsedToday);
                                
                                if (this.wheelWinReward > 0) {
                                    this.showToast(`🎉 恭喜获得 ${this.wheelWinReward} 积分！`, 'success');
                                }
                            }, 500);
                        }
                    }, speed);
                } else {
                    this.wheelSpinning = false;
                    this.wheelLightIndex = -1;
                    this.showToast(json.message || '抽奖失败', 'error');
                }
            } catch (e) {
                this.wheelSpinning = false;
                this.wheelLightIndex = -1;
                this.showToast('网络错误', 'error');
            }
        },
        
        // 🎲 猜数字方法
        async loadGuessConfig() {
            try {
                const res = await fetch('/api/points/config');
                const json = await res.json();
                if (json.status === 'success') {
                    const d = json.data;
                    this.guessEnabled = d.enable_guess === '1';
                    this.guessCost = parseInt(d.guess_cost) || 5;
                    this.guessRange = d.guess_range || '1-100';
                    const rangeParts = this.guessRange.split('-');
                    this.guessMin = parseInt(rangeParts[0]) || 1;
                    this.guessMax = parseInt(rangeParts[1]) || 100;
                    this.guessMaxTries = parseInt(d.guess_max_tries) || 7;
                    this.guessBaseReward = parseInt(d.guess_base_reward) || 50;
                    this.guessMultipliers = [
                        parseFloat(d.guess_multiplier_1) || 5,
                        parseFloat(d.guess_multiplier_2) || 3,
                        parseFloat(d.guess_multiplier_3) || 2,
                        1.5, 1.2, 1, 0.8
                    ];
                }
            } catch (e) {
                console.error('加载猜数字配置失败', e);
            }
        },
        
        openGuessGame() {
            if (!this.guessEnabled) {
                this.showToast('猜数字功能未启用', 'error');
                return;
            }
            this.guessGameOpen = true;
            this.resetGuessGame();
        },
        
        async startGuessGame() {
            if (this.userPoints < this.guessCost) {
                this.showToast('积分不足', 'error');
                return;
            }
            
            try {
                const res = await fetch('/api/guess/start', { method: 'POST' });
                const json = await res.json();
                
                if (json.status === 'success') {
                    this.guessPlaying = true;
                    this.guessTargetNumber = json.target_number;
                    this.guessTriesLeft = this.guessMaxTries;
                    this.guessHistory = [];
                    this.guessHint = '';
                    this.guessResult = '';
                    this.guessWon = false;
                    this.guessReward = 0;
                    this.userPoints = json.new_points || this.userPoints;
                } else {
                    this.showToast(json.message || '开始失败', 'error');
                }
            } catch (e) {
                this.showToast('网络错误', 'error');
            }
        },
        
        async submitGuess() {
            const num = parseInt(this.guessInput);
            if (isNaN(num) || num < this.guessMin || num > this.guessMax) {
                this.showToast(`请输入 ${this.guessMin}-${this.guessMax} 之间的数字`, 'error');
                return;
            }
            
            this.guessSubmitting = true;
            
            try {
                const res = await fetch('/api/guess/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ guess: num })
                });
                const json = await res.json();
                
                if (json.status === 'success') {
                    this.guessHistory.push(num);
                    this.guessTriesLeft = json.tries_left;
                    this.guessHint = json.hint || '';
                    
                    if (json.won) {
                        this.guessWon = true;
                        this.guessReward = json.reward;
                        this.guessResult = `🎉 恭喜猜对了！答案就是 ${num}`;
                        this.userPoints = json.new_points || this.userPoints;
                        this.guessPlaying = false;
                    } else if (json.game_over) {
                        this.guessWon = false;
                        this.guessResult = `😢 游戏结束！答案是 ${json.answer}`;
                        this.guessPlaying = false;
                    }
                    
                    this.guessInput = '';
                    this.guessSubmitting = false;
                } else {
                    this.guessSubmitting = false;
                    this.showToast(json.message || '猜测失败', 'error');
                }
            } catch (e) {
                this.guessSubmitting = false;
                this.showToast('网络错误', 'error');
            }
        },
        
        resetGuessGame() {
            this.guessPlaying = false;
            this.guessTargetNumber = 0;
            this.guessTriesLeft = this.guessMaxTries;
            this.guessHistory = [];
            this.guessInput = '';
            this.guessHint = '';
            this.guessResult = '';
            this.guessWon = false;
            this.guessReward = 0;
        },
        
        // 🎟️ 彩票方法
        async loadLotteryConfig() {
            try {
                const res = await fetch('/api/points/config');
                const json = await res.json();
                if (json.status === 'success') {
                    const d = json.data;
                    this.lotteryEnabled = d.enable_lottery === '1';
                    this.lotteryCost = parseInt(d.lottery_cost) || 100;
                    this.lotteryMaxPerDay = parseInt(d.lottery_max_per_day) || 10;
                    this.lotteryDrawHour = parseInt(d.lottery_draw_hour) || 20;
                }
                
                // 加载奖池和我的彩票
                await this.loadLotteryPool();
            } catch (e) {
                console.error('加载彩票配置失败', e);
            }
        },
        
        async loadLotteryPool() {
            try {
                const res = await fetch('/api/lottery/pool');
                const json = await res.json();
                console.log('[彩票] 奖池API返回:', json);
                if (json.status === 'success' && json.data) {
                    const data = json.data;
                    this.lotteryPool = data.today_pool || 0;
                    this.lotteryTodayTickets = data.user_today_tickets || 0;  // 🔥 使用用户购票数
                    this.lotteryMaxPerDay = data.max_per_day || 10;
                    this.lotteryNextDrawTime = data.next_draw_time || '';
                    this.lotteryTodayResult = data.today_winning_number || null;
                    this.lotteryIsDrawn = data.is_drawn || false;
                    this.lotteryMyWinning = data.my_winning_tickets || [];
                    this.lotteryMyPrizeTotal = data.my_prize_total || 0;
                    console.log('[彩票] 解析后:', {
                        pool: this.lotteryPool,
                        myTickets: this.lotteryTodayTickets,
                        nextTime: this.lotteryNextDrawTime,
                        isDrawn: this.lotteryIsDrawn
                    });
                }
                
                // 加载我的彩票
                await this.loadMyTickets();
                
                // 加载开奖结果
                await this.loadLotteryResults();
            } catch (e) {
                console.error('加载奖池失败', e);
            }
        },
        
        // 🔥 PWA 主题相关方法
        async loadPwaIcons() {
            this.iconsLoading = true;
            try {
                const res = await fetch('/api/pwa/icons');
                const json = await res.json();
                if (json.status === 'success') {
                    this.availableIcons = json.icons;
                }
                
                // 获取当前用户选择的图标
                const userRes = await fetch('/api/pwa/user_icon');
                const userJson = await userRes.json();
                if (userJson.status === 'success' && userJson.icon_id) {
                    this.currentIcon = userJson.icon_id;
                }
            } catch (e) {
                console.error('加载图标失败', e);
            }
            this.iconsLoading = false;
        },
        
        async selectIcon(iconId) {
            if (this.currentIcon === iconId) return;
            
            try {
                // 保存到数据库
                const res = await fetch('/api/pwa/set_user_icon', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ icon_id: iconId })
                });
                const json = await res.json();
                
                if (json.status === 'success') {
                    this.currentIcon = iconId;
                    
                    // 更新 manifest
                    const link = document.querySelector('link[rel="manifest"]');
                    if (link) {
                        link.href = `/api/pwa/manifest.json?t=${Date.now()}`;
                    }
                    
                    // 提示用户
                    this.showToast('图标已设置，卸载后重新安装 PWA 应用即可生效', 'success');
                } else {
                    this.showToast(json.detail || '设置失败', 'error');
                }
            } catch (e) {
                console.error('设置图标失败', e);
                this.showToast('设置图标失败', 'error');
            }
        },
        
        async loadLotteryResults() {
            try {
                const res = await fetch('/api/lottery/results');
                const json = await res.json();
                console.log('[彩票] 开奖结果API返回:', json);
                if (json.status === 'success') {
                    this.lotteryHistory = json.results || [];
                }
            } catch (e) {
                console.error('加载开奖结果失败', e);
            }
        },
        
        async loadMyTickets() {
            try {
                const res = await fetch('/api/lottery/my_tickets');
                const json = await res.json();
                if (json.status === 'success') {
                    this.lotteryMyTickets = json.tickets || [];
                }
            } catch (e) {
                console.error('加载我的彩票失败', e);
            }
        },
        
        openLotteryGame() {
            if (!this.lotteryEnabled) {
                this.showToast('彩票功能未启用', 'error');
                return;
            }
            this.lotteryGameOpen = true;
            this.lotteryBuyCount = 1;
            this.loadLotteryPool();
        },
        
        async buyLottery() {
            if (this.lotteryBuying) return;
            
            const totalCost = this.lotteryBuyCount * this.lotteryCost;
            if (this.userPoints < totalCost) {
                this.showToast('积分不足', 'error');
                return;
            }
            
            // 检查自选号码
            let customNumber = null;
            if (!this.lotteryAutoPick) {
                // 检查每个输入框是否都有值
                const hasEmpty = this.lotteryCustomNumber.some(n => !n || n.trim() === '');
                if (hasEmpty) {
                    this.showToast('请输入完整的4位号码', 'error');
                    return;
                }
                // 合并4位数字
                customNumber = this.lotteryCustomNumber.join('');
                // 验证是否为4位数字
                if (customNumber.length !== 4 || !/^[0-9]{4}$/.test(customNumber)) {
                    this.showToast('请输入4位数字（0000-9999）', 'error');
                    return;
                }
            }
            
            this.lotteryBuying = true;
            
            try {
                const res = await fetch('/api/lottery/buy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        count: this.lotteryBuyCount,
                        custom_number: customNumber
                    })
                });
                const json = await res.json();
                
                if (json.status === 'success') {
                    this.userPoints = json.new_points || this.userPoints;
                    this.lotteryTodayTickets = json.today_tickets || this.lotteryTodayTickets;
                    // 合并新购买的彩票号到现有列表
                    const newTickets = json.tickets || [];
                    this.lotteryMyTickets = [...this.lotteryMyTickets, ...newTickets];
                    this.lotteryBuying = false;
                    this.showToast(`🎟️ 成功购买 ${this.lotteryBuyCount} 张彩票！`, 'success');
                    this.lotteryBuyCount = 1;
                    this.lotteryCustomNumber = ['', '', '', ''];
                    // 刷新奖池
                    await this.loadLotteryPool();
                } else {
                    this.lotteryBuying = false;
                    this.showToast(json.message || '购买失败', 'error');
                }
            } catch (e) {
                this.lotteryBuying = false;
                this.showToast('网络错误', 'error');
            }
        },
        
        openMySeriesModal() {
            this.mySeriesModalOpen = true;
            this.mySeriesLoading = true;
            this.mySeries = [];
            this.selectedSeries = null;
            this.selectedEpisodesBySeason = {};
            this.mySeriesCacheInfo = { exists: false, expired: false, updated_at: '', interval_hours: 6 };
            fetch('/api/user/my_series')
                .then(r => r.json())
                .then(res => {
                    if (res.status === 'success') {
                        this.mySeries = res.data || [];
                        this.updateCostInfo = res.update_cost_info || { enabled: false, cost: 0, mode: 'per_series', base_cost: 0 };
                        this.mySeriesCacheInfo = res.cache_info || { exists: false, expired: false, updated_at: '', interval_hours: 6 };
                    } else {
                        this.showToast(res.message || '加载失败', 'error');
                    }
                })
                .catch(() => {
                    this.showToast('网络错误', 'error');
                })
                .finally(() => {
                    this.mySeriesLoading = false;
                });
        },
        
        refreshMySeriesCache() {
            this.mySeriesRefreshing = true;
            fetch('/api/user/my_series/refresh', { method: 'POST' })
                .then(r => r.json())
                .then(res => {
                    if (res.status === 'success') {
                        this.showToast(res.message || '已触发扫描', 'success');
                        setTimeout(() => {
                            this.mySeriesLoading = true;
                            fetch('/api/user/my_series')
                                .then(r => r.json())
                                .then(res2 => {
                                    if (res2.status === 'success') {
                                        this.mySeries = res2.data || [];
                                        this.mySeriesCacheInfo = res2.cache_info || this.mySeriesCacheInfo;
                                    }
                                })
                                .finally(() => {
                                    this.mySeriesLoading = false;
                                    this.mySeriesRefreshing = false;
                                });
                        }, 5000);
                    } else {
                        this.showToast(res.message || '刷新失败', 'error');
                        this.mySeriesRefreshing = false;
                    }
                })
                .catch(() => {
                    this.showToast('网络错误', 'error');
                    this.mySeriesRefreshing = false;
                });
        },
        
        selectSeriesForUpdate(series) {
            this.selectedSeries = series;
            this.selectedEpisodesBySeason = {};
            // 初始化每季的空数组
            if (series.seasons) {
                series.seasons.forEach(s => {
                    this.selectedEpisodesBySeason[s.season] = [];
                });
            }
        },
        
        // 🔥 按季选择集数的方法
        toggleEpisodeBySeason(season, ep) {
            const key = season.toString();
            if (!this.selectedEpisodesBySeason[key]) {
                this.selectedEpisodesBySeason[key] = [];
            }
            const idx = this.selectedEpisodesBySeason[key].indexOf(ep);
            if (idx > -1) {
                this.selectedEpisodesBySeason[key].splice(idx, 1);
            } else {
                this.selectedEpisodesBySeason[key].push(ep);
            }
            // 强制触发 Alpine 更新
            this.selectedEpisodesBySeason = {...this.selectedEpisodesBySeason};
        },
        
        isEpisodeSelected(season, ep) {
            const key = season.toString();
            return this.selectedEpisodesBySeason[key]?.includes(ep) || false;
        },
        
        selectAllSeasonEpisodes(season, eps) {
            const key = season.toString();
            if (!eps || !eps.length) return;
            if (this.isSeasonAllSelected(season, eps)) {
                this.selectedEpisodesBySeason[key] = [];
            } else {
                this.selectedEpisodesBySeason[key] = [...eps];
            }
            this.selectedEpisodesBySeason = {...this.selectedEpisodesBySeason};
        },
        
        clearSeasonEpisodes(season) {
            const key = season.toString();
            this.selectedEpisodesBySeason[key] = [];
            this.selectedEpisodesBySeason = {...this.selectedEpisodesBySeason};
        },
        
        isSeasonAllSelected(season, eps) {
            const key = season.toString();
            if (!eps || !eps.length) return false;
            const selected = this.selectedEpisodesBySeason[key] || [];
            return selected.length === eps.length;
        },
        
        getTotalSelectedEpisodes() {
            let total = 0;
            for (const key in this.selectedEpisodesBySeason) {
                total += (this.selectedEpisodesBySeason[key]?.length || 0);
            }
            return total;
        },
        
        // 🔥 根据收费模式计算实际扣分
        calculateUpdateCost() {
            if (!this.updateCostInfo.enabled) return 0;
            const mode = this.updateCostInfo.mode || 'per_series';
            // 🔥 修复：使用 !== undefined 判断，允许值为 0
            let baseCost = 20;  // 默认值
            if (this.updateCostInfo.base_cost !== undefined) {
                baseCost = this.updateCostInfo.base_cost;
            } else if (this.updateCostInfo.cost !== undefined) {
                baseCost = this.updateCostInfo.cost;
            }
            
            if (mode === 'per_series') {
                // 按剧收费：只扣一次
                return baseCost;
            } else if (mode === 'per_season') {
                // 按季收费：按有选择的季数扣分
                const seasonCount = Object.keys(this.selectedEpisodesBySeason).filter(k => this.selectedEpisodesBySeason[k]?.length > 0).length;
                return baseCost * seasonCount;
            } else if (mode === 'per_episode') {
                // 按集收费：按集数扣分
                return baseCost * this.getTotalSelectedEpisodes();
            }
            return baseCost;
        },
        
        // 🔥 判断集数是否已在追新中
        isEpisodeAlreadyRequested(seasonInfo, ep) {
            const status = seasonInfo.request_status;
            if (!status) return false;
            // 只有待审批(0)、下载中(1)、手动接单(4)、待入库(7)才算"追新中"
            if (status.status === undefined || [0, 1, 4, 7].indexOf(status.status) === -1) return false;
            const requestedEps = (status.episodes || '').split(',').map(e => parseInt(e)).filter(e => !isNaN(e));
            return requestedEps.indexOf(ep) !== -1;
        },
        
        // 🔥 判断是否可以选择该集数
        canSelectEpisode(seasonInfo, ep) {
            return !this.isEpisodeAlreadyRequested(seasonInfo, ep);
        },
        
        // 🔥 获取已追新的集数列表
        getAlreadyRequestedEpisodes(seasonInfo) {
            const status = seasonInfo.request_status;
            if (!status) return [];
            if (status.status === undefined || [0, 1, 4, 7].indexOf(status.status) === -1) return [];
            return (status.episodes || '').split(',').filter(e => e.trim());
        },
        
        // 🔥 获取集数按钮样式
        getEpisodeButtonClass(seasonInfo, ep) {
            if (this.isEpisodeAlreadyRequested(seasonInfo, ep)) {
                // 已追新：禁用样式
                return 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400 cursor-not-allowed opacity-60';
            }
            if (this.isEpisodeSelected(seasonInfo.season, ep)) {
                // 已选中：橙色
                return 'bg-orange-500 text-white shadow-md';
            }
            // 未选中：灰色可点击
            return 'bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-slate-400 hover:bg-orange-100 dark:hover:bg-orange-500/20';
        },
        
        // 🔥 提交多季追新请求（一次性批量提交）
        submitMultiSeasonUpdateRequest() {
            if (!this.selectedSeries || this.getTotalSelectedEpisodes() === 0) return;
            
            this.submittingUpdate = true;
            
            // 🔥 按季构建请求列表
            const requests = [];
            for (const season in this.selectedEpisodesBySeason) {
                const eps = this.selectedEpisodesBySeason[season];
                if (eps && eps.length > 0) {
                    requests.push({
                        series_id: this.selectedSeries.series_id,
                        tmdb_id: this.selectedSeries.tmdb_id,
                        title: this.selectedSeries.series_name,
                        year: this.selectedSeries.year || '',
                        poster_path: this.selectedSeries.poster || '',
                        season: parseInt(season),
                        episodes: eps.sort((a, b) => a - b)
                    });
                }
            }
            
            if (requests.length === 0) {
                this.submittingUpdate = false;
                return;
            }
            
            // 🔥 一次性批量提交所有季（后端统一扣分）
            fetch('/api/user/request_update_batch', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    requests: requests,
                    series_name: this.selectedSeries.series_name,
                    tmdb_id: this.selectedSeries.tmdb_id
                })
            })
            .then(r => r.json())
            .then(res => {
                if (res.status === 'success') {
                    this.showToast(`成功提交追新请求`, 'success');
                    this.selectedSeries = null;
                    this.selectedEpisodesBySeason = {};
                    // 刷新列表显示状态
                    this.mySeriesLoading = true;
                    fetch('/api/user/my_series')
                        .then(r => r.json())
                        .then(res => {
                            if (res.status === 'success') {
                                this.mySeries = res.data || [];
                            }
                        })
                        .finally(() => {
                            this.mySeriesLoading = false;
                        });
                } else {
                    this.showToast(res.message || '提交失败', 'error');
                }
            })
            .catch(() => {
                this.showToast('网络错误', 'error');
            })
            .finally(() => {
                this.submittingUpdate = false;
            });
        },
        
        getRequestStatusText(status) {
            const statusMap = {
                0: '待审批',
                1: '下载中',
                2: '已完成',
                3: '已拒绝',
                4: '手动接单',
                7: '待入库'
            };
            return statusMap[status] || '未知';
        },
        
        getRequestStatusClass(status) {
            const classMap = {
                0: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-500/20 dark:text-yellow-400',
                1: 'bg-blue-100 text-blue-700 dark:bg-blue-500/20 dark:text-blue-400',
                2: 'bg-green-100 text-green-700 dark:bg-green-500/20 dark:text-green-400',
                3: 'bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400',
                4: 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-400',
                7: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-400'
            };
            return classMap[status] || 'bg-gray-100 text-gray-700';
        },
        
        // 🔥 媒体库设置方法
        loadLibrarySettings() {
            this.libSettingsLoading = true;
            this.libList = [];
            fetch('/api/user/libraries')
                .then(r => r.json())
                .then(res => {
                    if (res.status === 'success') {
                        this.libList = res.data || [];
                        // 保存原始隐藏ID列表
                        this.libHiddenIds = this.libList.filter(l => l.hidden).map(l => l.id);
                    } else {
                        this.showToast(res.message || '加载失败', 'error');
                    }
                })
                .catch(() => {
                    this.showToast('网络错误', 'error');
                })
                .finally(() => {
                    this.libSettingsLoading = false;
                });
        },
        
        toggleLibrary(libId) {
            const lib = this.libList.find(l => l.id === libId);
            if (lib) {
                lib.hidden = !lib.hidden;
            }
        },
        
        saveLibrarySettings() {
            this.libSettingsSaving = true;
            const hiddenIds = this.libList.filter(l => l.hidden).map(l => l.id);
            fetch('/api/user/hidden_libraries', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hidden_libraries: hiddenIds })
            })
                .then(r => r.json())
                .then(res => {
                    if (res.status === 'success') {
                        this.showToast(res.message || '设置已保存', 'success');
                        this.libHiddenIds = hiddenIds;
                        setTimeout(() => {
                            this.libSettingsModalOpen = false;
                        }, 1500);
                    } else {
                        this.showToast(res.message || '保存失败', 'error');
                    }
                })
                .catch(() => {
                    this.showToast('网络错误', 'error');
                })
                .finally(() => {
                    this.libSettingsSaving = false;
                });
        },
        
        // 🔥 单季集数选择方法（兼容 tab_profile.html）
        toggleEpisodeSelection(ep) {
            const idx = this.selectedEpisodes.indexOf(ep);
            if (idx > -1) {
                this.selectedEpisodes.splice(idx, 1);
            } else {
                this.selectedEpisodes.push(ep);
            }
        },
        
        selectAllMissingEpisodes() {
            if (!this.selectedSeries?.seasons?.[0]?.missing_eps) return;
            const allEps = this.selectedSeries.seasons[0].missing_eps;
            if (this.selectedEpisodes.length === allEps.length) {
                this.selectedEpisodes = [];
            } else {
                this.selectedEpisodes = [...allEps];
            }
        },
        
        // 🔥 清空所有选中的集数
        clearAllEpisodes() {
            this.selectedEpisodes = [];
        },
        
        submitUpdateRequest() {
            if (!this.selectedSeries || !this.selectedEpisodes.length) return;
            
            this.submittingUpdate = true;
            
            // 🔥 从 selectedSeries 中获取季号（单季模式）
            const season = this.selectedSeries?.seasons?.[0]?.season || 1;
            
            fetch('/api/user/request_update', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    series_id: this.selectedSeries.series_id,
                    tmdb_id: this.selectedSeries.tmdb_id,
                    title: this.selectedSeries.series_name,
                    year: this.selectedSeries.year || '',
                    poster_path: this.selectedSeries.poster || '',
                    season: season,  // 🔥 修复：使用正确的季号
                    episodes: this.selectedEpisodes
                })
            })
            .then(r => r.json())
            .then(res => {
                if (res.status === 'success') {
                    this.showToast(res.message || '追新请求已提交', 'success');
                    this.selectedSeries = null;
                    this.selectedEpisodes = [];
                    this.openMySeriesModal();
                } else {
                    this.showToast(res.message || '提交失败', 'error');
                }
            })
            .catch(() => {
                this.showToast('网络错误', 'error');
            })
            .finally(() => {
                this.submittingUpdate = false;
            });
        },
        async login() { 
            if(!this.loginForm.username) return; 
            this.isLoggingIn = true; 
            try { 
                const res = await fetch('/api/requests/auth', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.loginForm) }); 
                const data = await res.json(); 
                if (data.status === 'success') { 
                    const checkRes = await fetch('/api/requests/check'); 
                    const checkData = await checkRes.json(); 
                    if (checkData.status === 'success') { 
                        this.userId = checkData.user.Id; 
                        this.userName = checkData.user.Name; 
                        this.expireDate = checkData.user.expire_date; 
                        this.serverUrl = checkData.server_url; 
                    } 
                    this.isLoggedIn = true; 
                    // 🔥 登录成功后加载所有数据
                    this.loadServerData(); 
                    this.loadUserMessages();
                    this.loadAnnouncements();
                    this.loadPointsData();
                    this.loadRequestCostConfig();
                    
                    // 🔥 如果当前在个人中心 tab，加载统计数据
                    if (this.currentTab === 'profile') {
                        this.loadProfileStats();
                    }
                    
                    if (data.expired) {
                        this.showToast(data.message || '账号已过期，请及时续费', 'error');
                    } else {
                        this.showToast('登录成功');
                    }
                } else {
                    this.showToast(data.message, 'error'); 
                } 
            } catch(e) { 
                this.showToast('网络错误', 'error'); 
            } 
            this.isLoggingIn = false; 
        },
        
        // 🔥 注册函数
        async handleRegister() {
            if(!this.registerForm.code || !this.registerForm.username || !this.registerForm.password) {
                this.showToast('请填写完整信息', 'error');
                return;
            }
            
            if(this.registerForm.username.length < 2) {
                this.showToast('用户名至少2个字符', 'error');
                return;
            }
            
            if(this.registerForm.password.length < 8) {
                this.showToast('密码至少8个字符', 'error');
                return;
            }
            
            this.isRegistering = true;
            
            try {
                const res = await fetch('/api/requests/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.registerForm)
                });
                const data = await res.json();
                
                if (data.status === 'success') {
                    // 注册成功，自动登录
                    this.userId = data.user.Id;
                    this.userName = data.user.Name;
                    this.expireDate = data.expire_date || '永久';
                    this.serverUrl = data.server_url || '';
                    this.isLoggedIn = true;
                    
                    // 🔥 注册成功后加载所有数据
                    this.loadServerData();
                    this.loadUserMessages();
                    this.loadAnnouncements();
                    this.loadPointsData();
                    this.loadRequestCostConfig();
                    
                    // 🔥 显示欢迎弹窗（Quill 编辑器保存的是 HTML）
                    if (data.welcome_message) {
                        this.welcomeModal.message = data.welcome_message;
                    } else {
                        this.welcomeModal.message = '感谢您的注册！请遵守社区规则，享受观影乐趣。';
                    }
                    this.welcomeModal.expireText = data.expire_days === -1 ? '永久有效' : `${data.expire_days} 天`;
                    this.welcomeModal.password = this.registerForm.password; // 🔥 保存密码供显示
                    this.showWelcomePassword = false; // 默认隐藏密码
                    this.welcomeModal.show = true;
                    
                    // 清空 URL 参数（避免刷新时再次触发注册模式）
                    window.history.replaceState({}, document.title, window.location.pathname);
                    
                    // 清空注册表单
                    this.registerForm = { code: '', username: '', password: '' };
                } else {
                    this.showToast(data.message, 'error');
                }
            } catch(e) {
                this.showToast('网络错误', 'error');
            }
            
            this.isRegistering = false;
        },
        async handleLogin() {
            this.isLoggingIn = true;
            try {
                const res = await fetch('/api/requests/auth', { 
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify(this.loginForm) 
                });
                const data = await res.json();
                
                if (data.status === 'success') {
                    // 过期用户也允许登录
                    if (data.expired) {
                        this.showToast(data.message || '账号已过期，请及时续费', 'error');
                    }
                    // 🔥 强制清除缓存后刷新（防止显示其他用户的数据）
                    window.location.href = window.location.href.split('?')[0] + '?_t=' + Date.now();
                } else {
                    this.showToast(data.message, 'error');
                    this.isLoggingIn = false;
                }
            } catch(e) {
                this.showToast('网络错误', 'error');
                this.isLoggingIn = false;
            }
        },
        async logout() { 
            try { 
                await fetch('/api/requests/logout', { method: 'POST' }); 
                // 🔥 设置退出标记，防止刷新后自动重新登录
                sessionStorage.setItem('user_logout_redirect', 'true');
                window.location.reload(); 
            } catch (e) {
                sessionStorage.setItem('user_logout_redirect', 'true');
                window.location.reload();
            } 
        },

        async loadServerData() { 
            try { 
                const [dash, hub, lat, topM, topS] = await Promise.all([ 
                    fetch('/api/stats/dashboard?user_id=all').then(r => r.json()), 
                    fetch('/api/requests/hub_data').then(r => r.json()), 
                    // 🔥 这里将原来的 latest 替换成了带有安检门的 safe_latest
                    fetch('/api/requests/safe_latest?limit=15').then(r => r.json()), 
                    fetch('/api/requests/safe_top?category=Movie').then(r => r.json()), 
                    fetch('/api/requests/safe_top?category=Episode').then(r => r.json()) 
                ]);
                
                // 检测账号是否被删除
                if (lat.account_deleted || topM.account_deleted || topS.account_deleted) {
                    this.showToast('账号已被删除，请重新登录', 'error');
                    this.isLoggedIn = false;
                    sessionStorage.setItem('account_deleted_redirect', 'true');
                    try { await fetch('/api/requests/logout', { method: 'POST' }); } catch(e) {}
                    this.isLoaded = true;
                    return;
                }
                
                if (dash.status === 'success') this.serverDashboard = dash.data; 
                if (hub.status === 'success') { this.serverTopRated = hub.data.top_rated; this.serverGenres = hub.data.genres; } 
                if (lat.status === 'success') this.serverLatest = lat.data; 
                if (topM.status === 'success') this.serverTopMovies = topM.data; 
                if (topS.status === 'success') this.serverTopSeries = topS.data; 
            } catch(e) {} 
            this.loadRecommendations();
        },

        async loadRecommendations() {
            try { 
                const res = await fetch(`/api/requests/trending`); 
                const data = await res.json(); 
                if(data.status === 'success' && data.data && data.data.length > 0) { 
                    let validItems = data.data.sort(() => 0.5 - Math.random());
                    this.recommendResults = validItems;
                    const third = Math.ceil(validItems.length / 3);
                    this.recommendRow1 = validItems.slice(0, third);
                    this.recommendRow2 = validItems.slice(third, third * 2);
                    this.recommendRow3 = validItems.slice(third * 2);
                } 
            } catch(e) { console.log("无热门数据"); }
        },

        switchTab(tab) { 
            this.currentTab = tab; 
            // 🔥 更新 URL 参数（不刷新页面）
            const url = new URL(window.location);
            url.searchParams.set('tab', tab);
            window.history.replaceState({}, '', url);
            
            this.$nextTick(() => window.scrollTo(0, 0)); 
            if (tab === 'profile') { 
                if (!this.statsLoaded) this.loadProfileStats(); 
                else setTimeout(() => this.renderCharts(), 150); 
            } 
        },

        async openShowcaseModal(itemId, fallbackItem = null) { 
            const finalId = itemId || (fallbackItem ? fallbackItem.ItemId || fallbackItem.Id : ''); 
            this.showcaseModal.data = fallbackItem || { Name: '加载中...' }; 
            this.showcaseModal.open = true; 
            this.showcaseModal.isLoading = true; 
            document.body.style.overflow = 'hidden'; 
            try { 
                const res = await fetch(`/api/requests/item_info?item_id=${finalId}`); 
                if(res.ok) { 
                    const data = await res.json(); 
                    if (data.status === 'success') {
                        // 核心修复：合并数据，防止覆盖掉已有字段
                        this.showcaseModal.data = { ...fallbackItem, ...data.data }; 
                    }
                } 
            } catch(e) {} finally { this.showcaseModal.isLoading = false; } 
        },
       closeShowcaseModal() { this.showcaseModal.open = false; document.body.style.overflow = ''; },
        openQueueModal(tab) { this.queueModal.activeTab = tab; this.queueModal.open = true; document.body.style.overflow = 'hidden'; if(tab === 'request') this.loadQueue(); else this.loadMyFeedback(); },
        closeQueueModal() { this.queueModal.open = false; document.body.style.overflow = ''; },

        async submitRequest() { 
            if (this.activeItem.media_type === 'movie' && this.activeItem.local_status === 2) return; 
            this.isSubmitting = true; 
            const seasons = this.activeItem.media_type === 'tv' ? this.selectedSeasons.map(Number).filter(s => s > 0) : [0]; 
            if (this.activeItem.media_type === 'tv' && seasons.length === 0) { 
                this.showToast('❌ 请至少选择一季', 'error'); 
                this.isSubmitting = false; 
                return; 
            } 
            const payload = { 
                tmdb_id: this.activeItem.tmdb_id, 
                media_type: this.activeItem.media_type, 
                title: this.activeItem.title, 
                year: this.activeItem.year, 
                poster_path: this.activeItem.poster_path, 
                overview: this.activeItem.overview, 
                seasons: seasons 
            }; 
            try { 
                const res = await fetch('/api/requests/submit', { 
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify(payload) 
                }); 
                const text = await res.text(); 
                let data = {}; 
                try { 
                    data = JSON.parse(text); 
                } catch(e) { 
                    data = { message: text }; 
                }
                
                // 检测账号是否被删除
                if (data.account_deleted) {
                    this.showToast('账号已被删除，请重新登录', 'error');
                    this.isLoggedIn = false;
                    sessionStorage.setItem('account_deleted_redirect', 'true');
                    try { await fetch('/api/requests/logout', { method: 'POST' }); } catch(e) {}
                    this.isLoaded = true;
                    return;
                }
                
                if (res.ok && (data.status === 'success' || !data.detail)) { 
                    this.showToast('✅ ' + (data.message || '心愿已发送！')); 
                    this.closeModal(); 
                    this.openQueueModal('request'); 
                } else { 
                    this.showToast('❌ ' + (data.message || data.detail || '提交异常'), 'error'); 
                } 
            } catch (e) { 
                this.showToast('网络异常', 'error'); 
            } finally { 
                this.isSubmitting = false; 
            } 
        },
        openFeedbackModal(itemName, posterPath = '') { this.feedbackModal.itemName = itemName; this.feedbackModal.posterPath = posterPath; this.feedbackModal.issueType = '缺少字幕'; this.feedbackModal.desc = ''; this.feedbackModal.open = true; if(this.isModalOpen) this.closeModal(); if(this.showcaseModal.open) this.closeShowcaseModal(); },
        async submitFeedback() { 
            this.isFeedbackSubmitting = true; 
            try { 
                const res = await fetch('/api/requests/feedback/submit', { 
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/json' }, 
                    body: JSON.stringify({ 
                        item_name: this.feedbackModal.itemName, 
                        issue_type: this.feedbackModal.issueType, 
                        description: this.feedbackModal.desc, 
                        poster_path: this.feedbackModal.posterPath 
                    }) 
                }); 
                const text = await res.text(); 
                let data = {}; 
                try { 
                    data = JSON.parse(text); 
                } catch(e) { 
                    data = { message: text }; 
                }
                
                // 检测账号是否被删除
                if (data.account_deleted) {
                    this.showToast('账号已被删除，请重新登录', 'error');
                    this.isLoggedIn = false;
                    sessionStorage.setItem('account_deleted_redirect', 'true');
                    try { await fetch('/api/requests/logout', { method: 'POST' }); } catch(e) {}
                    this.isLoaded = true;
                    return;
                }
                
                if (res.ok && (data.status === 'success' || !data.detail)) { 
                    this.showToast(data.message || '反馈成功'); 
                    this.feedbackModal.open = false; 
                    this.openQueueModal('feedback'); 
                } else { 
                    this.showToast(data.message || data.detail || '报错失败', 'error'); 
                } 
            } catch(e) { 
                this.showToast('网络错误', 'error'); 
            } finally { 
                this.isFeedbackSubmitting = false; 
            } 
        },
        async searchMedia() { 
            if (!this.searchQuery.trim()) return; 
            this.isSearching = true; 
            if (this.currentTab !== 'request') this.currentTab = 'request'; 
            window.scrollTo(0, 0); 
            try { 
                const res = await fetch(`/api/requests/search?query=${encodeURIComponent(this.searchQuery)}`); 
                const data = await res.json();
                
                // 检测账号是否被删除
                if (data.account_deleted) {
                    this.showToast('账号已被删除，请重新登录', 'error');
                    this.isLoggedIn = false;
                    sessionStorage.setItem('account_deleted_redirect', 'true');
                    try { await fetch('/api/requests/logout', { method: 'POST' }); } catch(e) {}
                    this.isLoaded = true;
                    return;
                }
                
                if (data.status === 'success') { 
                    this.searchResults = data.data; 
                    if (data.data.length === 0) this.showToast('未找到结果', 'error'); 
                } 
            } catch (e) { 
                this.showToast('网络错误', 'error'); 
            } finally { 
                this.isSearching = false; 
            } 
        },

        async loadProfileStats() {
            if (!this.userId) return;
            this.isStatsLoading = true;
            
            // 🔥 先加载积分数据（优先级高）
            this.loadPointsData();
            
            try {
                const [stats, badges, trend] = await Promise.all([
                    fetch(`/api/stats/user_details?user_id=${this.userId}`).then(r => r.json()),
                    fetch(`/api/stats/badges?user_id=${this.userId}`).then(r => r.json()),
                    fetch(`/api/stats/trend?dimension=day&user_id=${this.userId}`).then(r => r.json())
                ]);
                if (stats.status === 'success') this.userStats = stats.data;
                if (badges.status === 'success') this.userBadges = badges.data;
                if (trend.status === 'success') this.userTrend = trend.data;
                this.statsLoaded = true;
                this.renderCharts();
            } catch(e) {
                console.log('加载画像失败:', e);
            }
            this.isStatsLoading = false;
        },
        
        // 🔥 加载积分数据
        async loadPointsData() {
            if (!this.isLoggedIn) return;
            this.isLoadingPoints = true;
            try {
                const res = await fetch('/api/user/points/info');
                const data = await res.json();
                if (data.status === 'success') {
                    this.points = data.data.points || 0;
                    this.userPoints = data.data.points || 0; // 🎰 同步到老虎机
                    this.hasCheckedIn = data.data.has_checked_in || false;
                    this.config = data.data.config || {};
                    // 解析签到奖励范围
                    const min = parseInt(this.config.checkin_min) || 10;
                    const max = parseInt(this.config.checkin_max) || 30;
                    this.checkinReward = Math.floor((min + max) / 2); // 显示平均值
                    
                    // 🔥 先设置加载完成，让积分立即显示
                    this.isLoadingPoints = false;
                    
                    // 🔥 并行加载所有游戏配置（不阻塞积分显示）
                    Promise.all([
                        this.loadSlotConfig(),
                        this.loadScratchConfig(),
                        this.loadWheelConfig(),
                        this.loadGuessConfig(),
                        this.loadLotteryConfig()
                    ]).catch(e => console.log('加载游戏配置失败:', e));
                }
            } catch(e) {
                console.log('加载积分失败:', e);
            }
            this.isLoadingPoints = false;
        },
        
        // 🔥 签到方法
        async checkIn(e) {
            if (this.hasCheckedIn || this.isCheckingIn) return;
            this.isCheckingIn = true;
            try {
                const res = await fetch('/api/user/points/checkin', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    this.hasCheckedIn = true;
                    this.checkinReward = data.reward || 0;
                    this.points = data.balance || (this.points + this.checkinReward);
                    this.showRewardBubble = true;
                    setTimeout(() => this.showRewardBubble = false, 3000);
                    this.showToast(`签到成功！获得 ${this.checkinReward} 积分`, 'success');
                } else {
                    this.showToast(data.message || '签到失败', 'error');
                }
            } catch(e) {
                this.showToast('签到失败', 'error');
            }
            this.isCheckingIn = false;
        },
        
        // 🔥 兑换商品
        async redeemItem(item) {
            if (this.isRedeeming) return;
            this.isRedeeming = true;
            try {
                const res = await fetch('/api/user/points/redeem', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ item_id: item.id })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    this.points -= item.cost;
                    this.redeemResult = {
                        show: true,
                        type: data.type || 'success',
                        title: data.title || '兑换成功',
                        message: data.message || ''
                    };
                } else {
                    this.showToast(data.message || '兑换失败', 'error');
                }
            } catch(e) {
                this.showToast('兑换失败', 'error');
            }
            this.isRedeeming = false;
        },
        
        // 🔥 加载积分明细
        async loadMyLogs(page = 1) {
            this.logsLoading = true;
            this.logsPage = page;
            try {
                const res = await fetch(`/api/user/points/logs?page=${page}&page_size=${this.logsPageSize}`);
                const data = await res.json();
                console.log('[积分明细] API返回:', data);
                if (data.status === 'success') {
                    this.myLogs = data.data || [];
                    this.logsTotal = data.total || 0;
                    this.logsTotalPages = data.total_pages || 0;
                    console.log('[积分明细] 总数:', this.logsTotal, '总页数:', this.logsTotalPages);
                } else {
                    console.error('[积分明细] 加载失败:', data);
                    this.myLogs = [];
                    this.logsTotal = 0;
                    this.logsTotalPages = 0;
                }
            } catch(e) {
                console.log('加载明细失败:', e);
                this.myLogs = [];
                this.logsTotal = 0;
                this.logsTotalPages = 0;
            }
            this.logsLoading = false;
        },
        
        // 🔥 积分明细翻页
        logsPrevPage() {
            if (this.logsPage > 1) this.loadMyLogs(this.logsPage - 1);
        },
        logsNextPage() {
            if (this.logsPage < this.logsTotalPages) this.loadMyLogs(this.logsPage + 1);
        },
        logsFirstPage() {
            this.loadMyLogs(1);
        },
        logsLastPage() {
            this.loadMyLogs(this.logsTotalPages);
        },
        
        // 🔥 积分引擎初始化（用于 tab_profile.html 的 x-init）
        pointsEngine() {
            if (this.isLoggedIn && !this.statsLoaded) {
                this.loadProfileStats();
            }
        },
        
        // 🔥 初始化积分（用于 tab_profile.html）
        initPoints() {
            if (this.isLoggedIn) {
                this.loadPointsData();
            }
        },

        renderCharts() {
            this.$nextTick(() => {
                try {
                    if (!window.Chart || !this.userStats) return;
                    const isDark = this.isDarkMode; const textColor = isDark ? '#a1a1aa' : '#64748b'; 
                    const macaronColors = ['#10b981', '#3b82f6', '#8b5cf6', '#6366f1', '#14b8a6', '#64748b'];
                    const warmColors = ['#f43f5e', '#f59e0b', '#ec4899', '#f97316', '#d946ef', '#64748b'];
                    
                    const hourlyData = this.userStats.hourly || {};
                    if (document.getElementById('profileHourChart')) { if (this.charts.hour) this.charts.hour.destroy(); const ctx = document.getElementById('profileHourChart').getContext('2d'); let labels = [], values = []; for(let i=0; i<24; i++) { labels.push(String(i).padStart(2, '0')); values.push(hourlyData[String(i).padStart(2, '0')] || 0); } this.charts.hour = new Chart(ctx, { type: 'bar', data: { labels, datasets: [{ data: values, backgroundColor: isDark ? '#818cf8' : '#6366f1', borderRadius: 4 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { color: textColor, font: {size: 9} } }, y: { display: false } } } }); }
                    
                    const trendData = this.userTrend || {};
                    if (document.getElementById('profileTrendChart') && Object.keys(trendData).length > 0) { if (this.charts.trend) this.charts.trend.destroy(); const ctx = document.getElementById('profileTrendChart').getContext('2d'); const labels = Object.keys(trendData).map(k => k.substring(5)); const values = Object.values(trendData).map(v => Math.round(v/3600)); this.charts.trend = new Chart(ctx, { type: 'line', data: { labels, datasets: [{ data: values, borderColor: isDark ? '#38bdf8' : '#0ea5e9', backgroundColor: isDark ? 'rgba(56,189,248,0.15)' : 'rgba(14,165,233,0.15)', fill: true, tension: 0.4, borderWidth: 2, pointRadius: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { color: textColor, maxTicksLimit: 6, font: {size: 9} } }, y: { display: false } } } }); }
                    
                    const devices = this.userStats.devices || [];
                    if (document.getElementById('profileDeviceChart') && devices.length > 0) {
                        if (this.charts.device) this.charts.device.destroy(); const ctx = document.getElementById('profileDeviceChart').getContext('2d'); let labels = [], values = [], others = 0;
                        devices.forEach((d, i) => { let name = d.Device || d.device || d.name || d.Client || '未知'; let val = d.Plays || d.count || 0; if(i<4){ labels.push(name); values.push(val); } else { others += val; } });
                        if(others > 0){ labels.push('其他'); values.push(others); }
                        this.charts.device = new Chart(ctx, { type: 'doughnut', data: { labels, datasets: [{ data: values, backgroundColor: macaronColors, borderWidth: 2, borderColor: isDark ? '#000' : '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: { position: 'right', labels: { boxWidth: 6, font: {size: 9}, color: textColor } } } } });
                    }
                    
                    const clients = this.userStats.clients || [];
                    if (document.getElementById('profileClientChart') && clients.length > 0) {
                        if (this.charts.client) this.charts.client.destroy(); const ctx = document.getElementById('profileClientChart').getContext('2d'); let labels = [], values = [], others = 0;
                        clients.forEach((c, i) => { let name = c.Client || c.client || c.name || '未知'; let val = c.Plays || c.count || 0; if(i<4){ labels.push(name); values.push(val); } else { others += val; } });
                        if(others > 0){ labels.push('其他'); values.push(others); }
                        this.charts.client = new Chart(ctx, { type: 'doughnut', data: { labels, datasets: [{ data: values, backgroundColor: warmColors, borderWidth: 2, borderColor: isDark ? '#000' : '#fff' }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: { legend: { position: 'right', labels: { boxWidth: 6, font: {size: 9}, color: textColor } } } } });
                    }
                } catch (e) { console.error("图表数据异常保护", e); }
            });
        },

        getMoviePct() { if (!this.userStats || !this.userStats.preference) return 50; const pref = this.userStats.preference; const total = pref.movie_plays + pref.episode_plays; if (total === 0) return 50; return Math.round((pref.movie_plays / total) * 100); },
        getPrefText() { const pct = this.getMoviePct(); if (pct === 50 && (!this.userStats || this.userStats.overview.total_plays === 0)) return "尚无观看记录，探索中..."; if (pct > 70) return "「沉浸长片爱好者，偏爱电影的光影」"; if (pct < 30) return "「剧情连贯控，追剧是最大乐趣」"; return "「雨露均沾，电影与剧集我全都要」"; },
        
        // 🔥 修复3：补上丢失的“全选/全消”函数引擎
        toggleSelectAllSeasons() {
            const availableSeasons = this.tvSeasons.filter(s => !s.exists_locally).map(s => s.season_number);
            if (this.selectedSeasons.length === availableSeasons.length && availableSeasons.length > 0) {
                this.selectedSeasons = []; // 已经全选了，就执行全消
            } else {
                this.selectedSeasons = availableSeasons; // 否则执行全选未入库的季
            }
        },

        async openModal(item) { this.activeItem = item; this.isModalOpen = true; this.tvSeasons = []; this.selectedSeasons = []; document.body.style.overflow = 'hidden'; if (item.media_type === 'tv') { this.isLoadingSeasons = true; try { const res = await fetch(`/api/requests/tv/${item.tmdb_id}`); const data = await res.json(); if (data.status === 'success') { this.tvSeasons = data.seasons; if (this.tvSeasons.some(s => s.exists_locally)) this.activeItem.local_status = 2; } } catch (e) {} this.isLoadingSeasons = false; } else if (item.media_type === 'movie') { this.isCheckingLocal = true; try { const res = await fetch(`/api/requests/check/movie/${item.tmdb_id}`); const data = await res.json(); if (data.status === 'success' && data.exists) this.activeItem.local_status = 2; } catch(e) {} this.isCheckingLocal = false; } },
        closeModal() { this.isModalOpen = false; document.body.style.overflow = ''; },
        async loadQueue() { try { const res = await fetch('/api/requests/my'); const data = await res.json(); if (data.status === 'success') this.myQueue = data.data; } catch (e) {} },
        async loadMyFeedback() { try { const res = await fetch('/api/requests/feedback/my'); const data = await res.json(); if (data.status === 'success') this.myFeedbacks = data.data; } catch (e) {} },
        
        async openMyPosterStudio() { this.posterStudio.open = true; document.body.style.overflow = 'hidden'; this.setMyPosterTheme('#1a1a1a', 'white', '#eab308'); await this.setMyPosterPeriod('month'); },
        closeMyPosterStudio() { this.posterStudio.open = false; document.body.style.overflow = ''; },
        setMyPosterTheme(bg, text, hl) { const canvas = document.getElementById('my-capture-target'); if(!canvas) return; canvas.style.setProperty('--p-theme-bg', bg); canvas.style.setProperty('--p-theme-text', text); canvas.style.setProperty('--p-theme-highlight', hl); this.posterStudio.useCoverBg = false; document.getElementById('my-poster-bg-img').style.opacity = '0'; if(text === '#333') { canvas.style.setProperty('--p-theme-pill-bg', '#e5e7eb'); canvas.style.setProperty('--p-theme-pill-text', '#1f2937'); canvas.style.setProperty('--p-theme-card', 'rgba(0,0,0,0.03)'); document.getElementById('my-poster-bg-gradient').style.background = 'transparent'; document.getElementById('my-p-footer').style.color = 'rgba(0,0,0,0.3)'; } else { canvas.style.setProperty('--p-theme-pill-bg', 'rgba(255,255,255,0.15)'); canvas.style.setProperty('--p-theme-pill-text', 'white'); canvas.style.setProperty('--p-theme-card', 'rgba(255,255,255,0.08)'); document.getElementById('my-poster-bg-gradient').style.background = 'linear-gradient(to bottom, rgba(0,0,0,0.1), rgba(0,0,0,0.5))'; document.getElementById('my-p-footer').style.color = 'rgba(255,255,255,0.4)'; } },
        toggleMyCoverBg() { this.posterStudio.useCoverBg = !this.posterStudio.useCoverBg; const bgImg = document.getElementById('my-poster-bg-img'); const canvas = document.getElementById('my-capture-target'); if(!this.posterStudio.useCoverBg) { bgImg.style.opacity = '0'; if(canvas.style.getPropertyValue('--p-theme-text') === '#333') document.getElementById('my-poster-bg-gradient').style.background = 'transparent'; else document.getElementById('my-poster-bg-gradient').style.background = 'linear-gradient(to bottom, rgba(0,0,0,0.1), rgba(0,0,0,0.5))'; } else { bgImg.style.opacity = '1'; canvas.style.setProperty('--p-theme-card', 'rgba(255,255,255,0.08)'); canvas.style.setProperty('--p-theme-pill-bg', 'rgba(255,255,255,0.15)'); canvas.style.setProperty('--p-theme-pill-text', 'white'); canvas.style.setProperty('--p-theme-text', 'white'); document.getElementById('my-poster-bg-gradient').style.background = 'linear-gradient(to bottom, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.8) 100%)'; document.getElementById('my-p-footer').style.color = 'rgba(255,255,255,0.5)'; if(this.posterStudio.top1BgBase64) bgImg.style.backgroundImage = `url('${this.posterStudio.top1BgBase64}')`; } },
        async setMyPosterPeriod(period) { this.posterStudio.period = period; const now = new Date(); const y = now.getFullYear(); const m = now.getMonth() + 1; if (period === 'year') this.posterStudio.periodLabel = `${y} 年度观影报告`; else if (period === 'month') this.posterStudio.periodLabel = `${y}年${m}月 观影报告`; else if (period === 'week') { const day = now.getDay() || 7; const start = new Date(now); start.setDate(now.getDate() - day + 1); const end = new Date(now); end.setDate(now.getDate() - day + 7); this.posterStudio.periodLabel = `${start.getMonth()+1}/${start.getDate()} - ${end.getMonth()+1}/${end.getDate()} 周报`; } else this.posterStudio.periodLabel = '历史全量 观影报告'; await this.loadMyPosterData(); },
        async loadMyPosterData() { this.posterStudio.isLoading = true; try { const avatarEl = document.getElementById('my-p-avatar'); const b64Avatar = await toBase64(`/api/proxy/user_image/${this.userId}`); if (b64Avatar && avatarEl) { avatarEl.style.backgroundImage = `url('${b64Avatar}')`; avatarEl.innerHTML = ''; } const res = await fetch(`/api/stats/poster_data?user_id=${this.userId}&period=${this.posterStudio.period}`); const json = await res.json(); const data = json.data; this.posterStudio.data = data; this.posterStudio.top1BgBase64 = null; if (data.plays > 0) { const list = data.top_list; const renderRank = async (rank, idx) => { if(list[idx]) { const realImg = document.getElementById(`my-rank${rank}-img`); if(!realImg) return; realImg.removeAttribute('data-fallback-done'); const b64 = await toBase64(`/api/proxy/smart_image?item_id=${list[idx].ItemId}&name=${encodeURIComponent(list[idx].ItemName)}&type=Primary`); if(b64) { realImg.src = b64; realImg.style.objectFit = "cover"; realImg.style.padding = "0"; if(rank === 1) { this.posterStudio.top1BgBase64 = await applyPhysicalBlur(b64); if(this.posterStudio.useCoverBg) document.getElementById('my-poster-bg-img').style.backgroundImage = `url('${this.posterStudio.top1BgBase64}')`; } } else { window.fallbackReportPoster(realImg, list[idx].ItemName); } } }; await Promise.all([renderRank(1, 0), renderRank(2, 1), renderRank(3, 2)]); const smPromises = []; const max = Math.min(list.length, 10); for(let i=3; i<max; i++) { smPromises.push((async () => { const b64 = await toBase64(`/api/proxy/smart_image?item_id=${list[i].ItemId}&name=${encodeURIComponent(list[i].ItemName)}&type=Primary`); const imgEl = document.getElementById(`my-sm-img-${i-3}`); if(imgEl) { if(b64) { imgEl.src = b64; imgEl.style.objectFit = "cover"; } else window.fallbackReportPoster(imgEl, list[i].ItemName); } })()); } await Promise.all(smPromises); const area = document.getElementById('my-mood-area'); if(area) { area.innerHTML = ''; let html = ''; const mood = data.mood_data; if(mood) { if(mood.genres && mood.genres.length > 0) { const iconMap = {'剧情': '🎬', '喜剧': '😂', '动作': '⚔️', '科幻': '🛸', '悬疑': '🕵️‍♂️', '爱情': '❤️', '动画': '🦄', '恐怖': '👻', '犯罪': '🔪'}; let tagsHtml = ''; mood.genres.forEach(g => tagsHtml += `<div class="my-mood-tag-pill"><span>${iconMap[g]||'🏷️'}</span> <span>${g}</span></div>`); html += `<div class="my-mood-card"><div class="my-mood-title">观影基因重组</div><div class="my-mood-tags-container">${tagsHtml}</div></div>`; } if(mood.binge_day) html += `<div class="my-mood-card"><div class="my-mood-title">极度沉迷时刻</div><div class="my-mood-data-container"><div class="my-mood-data-box"><div class="my-mood-data-val">${mood.binge_day.date}</div><div class="my-mood-data-sub">这一天最疯狂</div></div><div class="my-mood-data-box"><div class="my-mood-data-val">${mood.binge_day.hours} H</div><div class="my-mood-data-sub">一口气看了</div></div></div></div>`; if(mood.late_night) html += `<div class="my-mood-card"><div class="my-mood-title">深夜刺客出没</div><div class="my-mood-data-container"><div class="my-mood-data-box" style="flex:1;"><div class="my-mood-data-val">凌晨 ${mood.late_night.time}</div><div class="my-mood-data-sub">正在看: ${mood.late_night.name}</div></div></div></div>`; } area.innerHTML = html; } } this.$nextTick(() => { const wrapper = document.getElementById('my-poster-preview-area'); const scaleWrapper = document.getElementById('my-scale-wrapper'); if(wrapper && scaleWrapper) { const scale = Math.min((wrapper.clientWidth - 40) / 400, 1); scaleWrapper.style.transform = `scale(${scale})`; } }); } catch(e) {} this.posterStudio.isLoading = false; },
        async saveMyPoster() { this.posterStudio.isSaving = true; const scaleWrapper = document.getElementById('my-scale-wrapper'); const oldT = scaleWrapper.style.transform; document.getElementById('my-poster-preview-area').scrollTo(0, 0); scaleWrapper.style.transform = 'none'; await new Promise(r => setTimeout(r, 500)); try { const canvas = await html2canvas(document.getElementById('my-capture-target'), { scale: 2, useCORS: true, backgroundColor: null, scrollY: 0, scrollX: 0 }); const link = document.createElement('a'); link.download = `EmbyPulse_${this.userName}.png`; link.href = canvas.toDataURL(); link.click(); this.showToast('海报已保存！'); } catch(e) { this.showToast('生成失败', 'error'); } finally { scaleWrapper.style.transform = oldT; this.posterStudio.isSaving = false; } },

        async loadUserMessages() {
            if (!this.isLoggedIn) return;
            try {
                // 同时加载消息和禁言状态
                const [msgRes, muteRes] = await Promise.all([
                    fetch('/api/user/messages'),
                    fetch('/api/user/mute_status')
                ]);
                const msgData = await msgRes.json();
                const muteData = await muteRes.json();
                
                // 检测账号是否被删除
                if (msgData.account_deleted || muteData.account_deleted) {
                    this.showToast('账号已被删除，请重新登录', 'error');
                    this.isLoggedIn = false;
                    sessionStorage.setItem('account_deleted_redirect', 'true');
                    try { await fetch('/api/requests/logout', { method: 'POST' }); } catch(e) {}
                    this.isLoaded = true;
                    return;
                }
                
                if (msgData.status === 'success') {
                    this.userMessages = msgData.data.messages || [];
                    this.userUnreadCount = msgData.data.unread || 0;
                    this.$nextTick(() => {
                        const list = document.getElementById('user-message-list');
                        if (list) list.scrollTop = list.scrollHeight;
                    });
                }
                
                if (muteData.status === 'success') {
                    this.userMuteInfo = muteData.data;
                }
            } catch(e) {}
        },

        // 用户消息轮询
        startUserMsgPolling() {
            if (this._msgPollInterval) clearInterval(this._msgPollInterval);
            this._msgPollInterval = setInterval(() => {
                if (this.msgModalOpen && this.isLoggedIn) {
                    this.loadUserMessages();
                }
            }, 5000);
        },

        stopUserMsgPolling() {
            if (this._msgPollInterval) {
                clearInterval(this._msgPollInterval);
                this._msgPollInterval = null;
            }
        },

        // 🔥 打开消息弹窗
        openMsgModal() {
            this.msgModalOpen = true;
            this.loadUserMessages();
            this.startUserMsgPolling();
        },

        // 🔥 关闭消息弹窗
        closeMsgModal() {
            this.msgModalOpen = false;
            this.stopUserMsgPolling();
        },

        async sendUserMessage() {
            // 检查是否被禁言
            if (this.userMuteInfo && this.userMuteInfo.is_muted) {
                let msg = '您已被禁言，无法发送消息';
                if (this.userMuteInfo.reason) msg += `\n原因：${this.userMuteInfo.reason}`;
                if (this.userMuteInfo.until) msg += `\n解禁时间：${this.formatMuteUntil(this.userMuteInfo.until)}`;
                else msg += '\n禁言状态：永久';
                this.showToast(msg, 'error');
                return;
            }
            
            if (!this.userNewMessage.trim() || this.userSending) return;
            this.userSending = true;
            try {
                const res = await fetch('/api/user/messages/send', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: this.userNewMessage.trim() })
                });
                const data = await res.json();
                
                // 检测账号是否被删除
                if (data.account_deleted) {
                    this.showToast('账号已被删除，请重新登录', 'error');
                    this.isLoggedIn = false;
                    sessionStorage.setItem('account_deleted_redirect', 'true');
                    try { await fetch('/api/requests/logout', { method: 'POST' }); } catch(e) {}
                    this.isLoaded = true;
                    return;
                }
                
                if (data.status === 'success') {
                    this.userNewMessage = '';
                    await this.loadUserMessages();
                } else {
                    this.showToast(data.message || '发送失败', 'error');
                }
            } catch(e) {
                this.showToast('网络错误', 'error');
            }
            this.userSending = false;
        },

        formatMuteUntil(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
        },

        formatUserMsgTime(timeStr) {
            if (!timeStr) return '';
            const date = new Date(timeStr);
            const now = new Date();
            const isToday = date.toDateString() === now.toDateString();
            if (isToday) {
                return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            } else {
                return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
            }
        },

        // ==================== 公告相关 ====================
        async loadAnnouncements() {
            try {
                const res = await fetch('/api/user/announcements');
                const data = await res.json();
                if (data.status === 'success') {
                    this.announcements = data.data || [];
                    console.log('加载公告:', this.announcements.length, '条', this.announcements);
                    if (this.announcements.length > 0) {
                        // 🔥 使用 setTimeout 确保 DOM 完全渲染后再启动滚动
                        setTimeout(() => this.startAnnouncementScroll(), 100);
                        
                        // 🔥 检查是否有未读公告，自动弹出第一个未读公告
                        const unreadAnn = this.announcements.find(a => a.is_new);
                        if (unreadAnn) {
                            setTimeout(() => {
                                this.openAnnouncementDetail(unreadAnn);
                            }, 500);
                        }
                    }
                }
            } catch(e) {
                console.log('加载公告失败:', e);
            }
        },

        startAnnouncementScroll() {
            if (this.announcementScrollInterval) {
                clearInterval(this.announcementScrollInterval);
            }
            
            // 🔥 无论公告数量，都需要设置第一个公告项可见
            this.currentAnnouncementIndex = 0;
            this.updateAnnouncementVisibility();
            
            // 只有大于1条公告时才启动滚动
            if (this.announcements.length > 1) {
                this.announcementScrollInterval = setInterval(() => {
                    this.nextAnnouncement();
                }, 5000);
            }
        },

        nextAnnouncement() {
            if (this.announcements.length <= 1) return;
            this.currentAnnouncementIndex = (this.currentAnnouncementIndex + 1) % this.announcements.length;
            this.updateAnnouncementVisibility();
        },

        prevAnnouncement() {
            if (this.announcements.length <= 1) return;
            this.currentAnnouncementIndex = (this.currentAnnouncementIndex - 1 + this.announcements.length) % this.announcements.length;
            this.updateAnnouncementVisibility();
        },

        updateAnnouncementVisibility() {
            const items = document.querySelectorAll('.announcement-item');
            items.forEach((item, index) => {
                if (index === this.currentAnnouncementIndex) {
                    item.style.opacity = '1';
                    item.style.pointerEvents = 'auto';
                } else {
                    item.style.opacity = '0';
                    item.style.pointerEvents = 'none';
                }
            });
        },

        formatAnnouncementTime(timeStr) {
            if (!timeStr) return '';
            
            // 处理 SQLite 的 datetime('now','localtime') 格式
            let date;
            if (typeof timeStr === 'string') {
                // 尝试多种格式解析
                // 格式1: "2026-04-08 11:00:00" (SQLite local)
                // 格式2: "2026-04-08T11:00:00" (ISO without timezone)
                // 格式3: "2026-04-08T11:00:00+08:00" (ISO with timezone)
                if (timeStr.includes('T')) {
                    date = new Date(timeStr);
                } else {
                    // SQLite 格式，当作本地时间处理
                    date = new Date(timeStr.replace(' ', 'T'));
                }
            } else {
                date = new Date(timeStr);
            }
            
            // 检查日期是否有效
            if (isNaN(date.getTime())) {
                return timeStr;
            }
            
            const now = new Date();
            const diffMs = now.getTime() - date.getTime();
            const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
            
            if (diffDays === 0) {
                return '今天';
            } else if (diffDays === 1) {
                return '昨天';
            } else if (diffDays > 0 && diffDays < 7) {
                return `${diffDays}天前`;
            } else if (diffDays < 0) {
                // 未来时间，显示日期
                return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
            } else {
                return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
            }
        },

        openAnnouncementDetail(ann) {
            this.announcementDetail.data = ann;
            this.announcementDetail.index = this.announcements.findIndex(a => a.id === ann.id);
            this.announcementDetail.show = true;
            // 增加浏览次数
            fetch(`/api/announcements/${ann.id}/view`, { method: 'POST' }).catch(() => {});
            // 🔥 标记为已读
            if (ann.is_new) {
                ann.is_new = false;
                fetch(`/api/user/announcements/${ann.id}/read`, { method: 'POST' }).catch(() => {});
            }
        },

        closeAnnouncementDetail() {
            this.announcementDetail.show = false;
            this.announcementDetail.data = null;
        },
        
        // 🔥 修复未闭合的 HTML 标签
        fixUnclosedHtmlTags(html) {
            // 自闭合标签不需要修复
            const selfClosing = new Set(['br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'param', 'source', 'track', 'wbr']);
            
            const openTags = [];
            const result = [];
            let pos = 0;
            
            // 正则匹配所有标签
            const tagPattern = /<(\/)?(\w+)([^>]*)>/gi;
            let match;
            
            while ((match = tagPattern.exec(html)) !== null) {
                // 添加标签前的文本
                result.push(html.substring(pos, match.index));
                pos = match.index + match[0].length;
                
                const isClosing = match[1] === '/';
                const tagName = match[2].toLowerCase();
                const attrs = match[3] || '';
                
                // 跳过自闭合标签
                if (selfClosing.has(tagName) || attrs.trim().endsWith('/')) {
                    result.push(match[0]);
                    continue;
                }
                
                if (isClosing) {
                    // 闭合标签
                    if (openTags.length > 0 && openTags[openTags.length - 1] === tagName) {
                        openTags.pop();
                        result.push(match[0]);
                    } else if (openTags.includes(tagName)) {
                        // 闭合所有中间的标签
                        while (openTags.length > 0 && openTags[openTags.length - 1] !== tagName) {
                            const unclosed = openTags.pop();
                            result.push(`</${unclosed}>`);
                        }
                        if (openTags.length > 0) {
                            openTags.pop();
                            result.push(match[0]);
                        }
                    } else {
                        result.push(match[0]);
                    }
                } else {
                    // 开标签
                    openTags.push(tagName);
                    result.push(match[0]);
                }
            }
            
            // 添加剩余文本
            result.push(html.substring(pos));
            
            // 闭合所有未闭合的标签
            while (openTags.length > 0) {
                const tag = openTags.pop();
                result.push(`</${tag}>`);
            }
            
            return result.join('');
        },
        
        // 🔥 获取公告纯文本预览（用于滚动条显示）
        getAnnouncementPreview(content) {
            if (!content) return '';
            // 如果是 HTML，提取纯文本
            if (content.includes('<')) {
                // 移除所有 HTML 标签
                let text = content.replace(/<[^>]*>/g, '');
                // 解码 HTML 实体
                text = text.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&#039;/g, "'");
                return text.trim();
            }
            return content;
        },
        
        // 🔥 简易 Markdown 解析器
        parseMarkdown(text) {
            // 🔥 检测是否为富文本 HTML（来自 Quill 编辑器）
            // Quill 生成的 HTML 包含特定标签如 <p>, <span>, <strong>, <em>, <u>, <s>, <a>, <h1-h3>
            const isRichHtml = text.includes('<p') || 
                               text.includes('<span') || 
                               text.includes('<strong') || 
                               text.includes('<em') || 
                               text.includes('<h1') || 
                               text.includes('<h2') || 
                               text.includes('<h3') || 
                               text.includes('ql-');
            
            // 如果是富文本 HTML，直接返回（已由 Quill 格式化）
            if (isRichHtml) {
                // 只需处理一些样式增强
                let html = text;
                // 确保链接有正确的样式
                html = html.replace(/<a([^>]*)>/gi, '<a$1 style="color:#3b82f6;text-decoration:underline" target="_blank">');
                // 🔥 修复未闭合的 HTML 标签
                html = this.fixUnclosedHtmlTags(html);
                return html;
            }
            
            // 🔥 以下是 Markdown 解析逻辑（兼容旧数据）
            if (!text) return '';
            
            // 先转义 HTML 特殊字符
            let html = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
            
            // 恢复允许的 HTML 标签
            html = html
                .replace(/&lt;b&gt;/gi, '<b>').replace(/&lt;\/b&gt;/gi, '</b>')
                .replace(/&lt;strong&gt;/gi, '<strong>').replace(/&lt;\/strong&gt;/gi, '</strong>')
                .replace(/&lt;i&gt;/gi, '<i>').replace(/&lt;\/i&gt;/gi, '</i>')
                .replace(/&lt;em&gt;/gi, '<em>').replace(/&lt;\/em&gt;/gi, '</em>')
                .replace(/&lt;u&gt;/gi, '<u>').replace(/&lt;\/u&gt;/gi, '</u>')
                .replace(/&lt;s&gt;/gi, '<s>').replace(/&lt;\/s&gt;/gi, '</s>')
                .replace(/&lt;br\s*\/?&gt;/gi, '<br>')
                .replace(/&lt;font([^&]*)&gt;/gi, '<font$1>').replace(/&lt;\/font&gt;/gi, '</font>')
                .replace(/&lt;a\s+([^&]*)&gt;/gi, '<a $1>').replace(/&lt;\/a&gt;/gi, '</a>')
                .replace(/&lt;code&gt;/gi, '<code>').replace(/&lt;\/code&gt;/gi, '</code>');
            
            // 🔥 先处理 Markdown 链接（必须在其他行内格式之前）
            html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color:#3b82f6;text-decoration:underline" target="_blank">$1</a>');
            
            // Markdown 解析（按行处理）
            const lines = html.split('\n');
            const result = [];
            let inList = false;
            let listType = '';
            
            for (let i = 0; i < lines.length; i++) {
                let line = lines[i];
                
                // 标题
                if (/^###\s+(.+)/.test(line)) {
                    line = line.replace(/^###\s+(.+)/, '<h3 style="font-size:0.95rem;font-weight:bold;margin:0.4rem 0">$1</h3>');
                } else if (/^##\s+(.+)/.test(line)) {
                    line = line.replace(/^##\s+(.+)/, '<h2 style="font-size:1rem;font-weight:bold;margin:0.4rem 0">$1</h2>');
                } else if (/^#\s+(.+)/.test(line)) {
                    line = line.replace(/^#\s+(.+)/, '<h1 style="font-size:1.1rem;font-weight:bold;margin:0.4rem 0">$1</h1>');
                }
                
                // 无序列表
                if (/^-\s+(.+)/.test(line)) {
                    if (!inList || listType !== 'ul') {
                        if (inList) result.push(`</${listType}>`);
                        result.push('<ul style="list-style:disc;margin-left:1rem;margin:0.2rem 0">');
                        inList = true;
                        listType = 'ul';
                    }
                    line = line.replace(/^-\s+(.+)/, '<li>$1</li>');
                }
                // 有序列表
                else if (/^\d+\.\s+(.+)/.test(line)) {
                    if (!inList || listType !== 'ol') {
                        if (inList) result.push(`</${listType}>`);
                        result.push('<ol style="list-style:decimal;margin-left:1rem;margin:0.2rem 0">');
                        inList = true;
                        listType = 'ol';
                    }
                    line = line.replace(/^\d+\.\s+(.+)/, '<li>$1</li>');
                }
                else {
                    if (inList) {
                        result.push(`</${listType}>`);
                        inList = false;
                        listType = '';
                    }
                }
                
                // 行内格式（链接已在前面处理）
                if (!/^<(h[1-6]|ul|ol|li)/.test(line)) {
                    // 先处理加粗 **文本** 或 __文本__
                    line = line.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
                    line = line.replace(/__(.+?)__/g, '<strong>$1</strong>');
                    // 再处理斜体 *文本* 或 _文本_（确保不是 ** 或 __）
                    line = line.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
                    line = line.replace(/_([^_\n]+)_/g, '<em>$1</em>');
                    // 删除线
                    line = line.replace(/~~(.+?)~~/g, '<s>$1</s>');
                    // 行内代码
                    line = line.replace(/`([^`]+)`/g, '<code style="background:rgba(0,0,0,0.1);padding:0.1rem 0.3rem;border-radius:0.25rem;font-size:0.9em">$1</code>');
                }
                
                result.push(line);
            }
            
            if (inList) result.push(`</${listType}>`);
            
            html = result.join('\n');
            html = html.replace(/\n/g, '<br>');
            html = html.replace(/<br>\s*<(h[1-6]|ul|ol|li|\/ul|\/ol)/gi, '<$1');
            html = html.replace(/(<\/h[1-6]|<\/ul|<\/ol|<\/li)>\s*<br>/gi, '$1>');
            
            return html;
        },
        
        // 🔥 复制公告内容
        copyAnnouncementContent() {
            if (!this.announcementDetail.data) return;
            const title = this.announcementDetail.data.title || '';
            const content = this.announcementDetail.data.content || '';
            const text = title + '\n\n' + content;
            
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    this.showToast('已复制到剪贴板', 'success');
                }).catch(() => {
                    this.fallbackCopy(text);
                });
            } else {
                this.fallbackCopy(text);
            }
        },
        
        // 降级复制方法
        fallbackCopy(text) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.left = '-9999px';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                this.showToast('已复制到剪贴板', 'success');
            } catch (e) {
                this.showToast('复制失败', 'error');
            }
            document.body.removeChild(textarea);
        },
        
    })); // 结束 Alpine.data
}); // 结束 alpine:init 事件监听

// 🔥 动态加载 Alpine.js（async 模式，不阻塞页面）
(function() {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js';
    script.async = true;
    document.head.appendChild(script);
})();