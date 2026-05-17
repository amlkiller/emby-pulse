"""
观影报告海报设计方案
提供3种不同风格供用户选择
"""

# 方案A: 极简卡片风格 (类似 Apple App Store Today)
def generate_poster_minimal(self, period, tv_list, movie_list, pc):
    """
    极简风格 - 大面积留白，卡片式布局
    - 适合喜欢简洁、现代感的用户
    - 白色/浅色背景，圆角卡片
    - 大封面 + 简洁文字
    """
    W, H = 800, 1200
    padding = 50
    
    # 浅色背景
    img = Image.new('RGB', (W, H), (250, 250, 252))
    draw = ImageDraw.Draw(img)
    
    # 顶部标题区 - 渐变色块
    for y in range(200):
        ratio = y / 200
        r = int(99 + ratio * 40)
        g = int(102 + ratio * 40)
        b = int(241 + ratio * 14)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    
    # 标题
    font_title = _get_font(48)
    font_sub = _get_font(20)
    font_name = _get_font(24)
    font_count = _get_font(16)
    
    draw.text((padding, 60), "观影榜单", font=font_title, fill=(255, 255, 255))
    draw.text((padding, 130), pc['date_label'], font=font_sub, fill=(255, 255, 255))
    
    current_y = 240
    
    # 绘制卡片
    def draw_card(item, rank, y_pos):
        card_h = 180
        # 卡片背景
        draw.rounded_rectangle([(padding, y_pos), (W-padding, y_pos+card_h)], 
                               radius=20, fill=(255, 255, 255))
        
        # 排名圆圈
        rank_colors = [(255, 200, 80), (180, 180, 190), (205, 150, 100)]
        color = rank_colors[rank-1] if rank <= 3 else (220, 220, 220)
        draw.ellipse([(padding+20, y_pos+60), (padding+80, y_pos+120)], fill=color)
        
        rank_font = _get_font(32)
        draw.text((padding+38, y_pos+72), str(rank), font=rank_font, fill=(255, 255, 255))
        
        # 封面
        poster_x = padding + 100
        poster = self._fetch_emby_poster(item.get('ItemId'), 100, 150)
        if poster:
            img.paste(poster, (poster_x, y_pos+15))
        
        # 标题和播放
        text_x = poster_x + 120
        title = item.get('SeriesName', item.get('ItemName', '未知'))[:15]
        draw.text((text_x, y_pos+50), title, font=font_name, fill=(30, 30, 30))
        draw.text((text_x, y_pos+90), f"{item.get('C', 0)} 次播放", font=font_count, fill=(120, 120, 120))
        
        return y_pos + card_h + 20
    
    # 绘制内容
    if tv_list:
        draw.text((padding, current_y), "热播剧集", font=font_sub, fill=(80, 80, 80))
        current_y += 50
        for i, item in enumerate(tv_list[:3]):
            current_y = draw_card(item, i+1, current_y)
    
    if movie_list:
        current_y += 20
        draw.text((padding, current_y), "热门电影", font=font_sub, fill=(80, 80, 80))
        current_y += 50
        for i, item in enumerate(movie_list[:3]):
            current_y = draw_card(item, i+1, current_y)
    
    return img


# 方案B: 暗黑霓虹风格 (类似 Cyberpunk)
def generate_poster_cyber(self, period, tv_list, movie_list, pc):
    """
    赛博朋克风格 - 暗黑背景 + 霓虹光效
    - 适合喜欢酷炫、科技感的用户
    - 深色背景，荧光色文字
    - 发光效果
    """
    W, H = 900, 1400
    padding = 60
    
    # 深色背景
    img = Image.new('RGB', (W, H), (15, 15, 25))
    draw = ImageDraw.Draw(img)
    
    # 霓虹网格线背景
    for i in range(0, W, 50):
        draw.line([(i, 0), (i, H)], fill=(40, 40, 60), width=1)
    for i in range(0, H, 50):
        draw.line([(0, i), (W, i)], fill=(40, 40, 60), width=1)
    
    # 顶部霓虹标题
    font_title = _get_font(64)
    font_sub = _get_font(24)
    font_name = _get_font(28)
    font_count = _get_font(18)
    
    # 发光标题效果
    for offset in range(10, 0, -2):
        alpha = int(50 - offset * 5)
        draw.text((padding+offset, 60+offset), "观影榜单", font=font_title, 
                 fill=(0, 255, 255, alpha))
    
    draw.text((padding, 60), "观影榜单", font=font_title, fill=(0, 255, 255))
    draw.text((padding, 140), pc['date_label'], font=font_sub, fill=(255, 0, 255))
    
    current_y = 260
    
    def draw_neon_item(item, rank, y_pos):
        # 霓虹边框
        draw.rounded_rectangle([(padding, y_pos), (W-padding, y_pos+200)], 
                               radius=10, outline=(0, 255, 255), width=2)
        
        # 排名 - 霓虹数字
        rank_font = _get_font(80)
        colors = [(255, 255, 0), (0, 255, 255), (255, 0, 255)]
        color = colors[rank-1] if rank <= 3 else (150, 150, 150)
        
        # 发光效果
        for i in range(5):
            draw.text((padding+20+i, y_pos+50+i), f"0{rank}", font=rank_font, 
                     fill=(color[0], color[1], color[2]))
        
        draw.text((padding+20, y_pos+50), f"0{rank}", font=rank_font, fill=color)
        
        # 封面
        poster = self._fetch_emby_poster(item.get('ItemId'), 120, 180)
        if poster:
            img.paste(poster, (padding+150, y_pos+10))
        
        # 文字
        title = item.get('SeriesName', item.get('ItemName', '未知'))[:12]
        draw.text((padding+300, y_pos+60), title, font=font_name, fill=(255, 255, 255))
        draw.text((padding+300, y_pos+110), f"{item.get('C', 0)} PLAYS", font=font_count, fill=(0, 255, 255))
        
        return y_pos + 220
    
    if tv_list:
        draw.text((padding, current_y), ">> TV SHOWS", font=font_sub, fill=(255, 0, 255))
        current_y += 50
        for i, item in enumerate(tv_list[:3]):
            current_y = draw_neon_item(item, i+1, current_y)
    
    if movie_list:
        current_y += 30
        draw.text((padding, current_y), ">> MOVIES", font=font_sub, fill=(255, 0, 255))
        current_y += 50
        for i, item in enumerate(movie_list[:3]):
            current_y = draw_neon_item(item, i+1, current_y)
    
    return img


# 方案C: 杂志封面风格 (类似 Vogue/时尚杂志)
def generate_poster_magazine(self, period, tv_list, movie_list, pc):
    """
    杂志封面风格 - 大图配大字
    - 适合喜欢时尚、艺术感的用户
    - 第一张封面占满上半部分
    - 大标题 + 简洁排版
    """
    W, H = 800, 1200
    padding = 40
    
    img = Image.new('RGB', (W, H), (20, 20, 25))
    draw = ImageDraw.Draw(img)
    
    # 获取第一名封面作为背景
    first_item = None
    if tv_list:
        first_item = tv_list[0]
    elif movie_list:
        first_item = movie_list[0]
    
    if first_item:
        poster = self._fetch_emby_poster(first_item.get('ItemId'), 800, 600)
        if poster:
            # 上半部分放封面
            img.paste(poster, (0, 0))
            # 渐变遮罩
            for y in range(400, 600):
                alpha = int((y - 400) / 200 * 255)
                draw.line([(0, y), (W, y)], fill=(20, 20, 25))
    
    font_title = _get_font(72)
    font_sub = _get_font(28)
    font_name = _get_font(32)
    font_rank = _get_font(120)
    
    # 大标题
    draw.text((padding, 520), "本期热门", font=font_title, fill=(255, 255, 255))
    draw.text((padding, 610), pc['date_label'], font=font_sub, fill=(200, 200, 200))
    
    current_y = 700
    
    # 列表展示
    all_items = []
    if tv_list:
        all_items.extend([('剧集', item) for item in tv_list[:2]])
    if movie_list:
        all_items.extend([('电影', item) for item in movie_list[:2]])
    
    for i, (type_name, item) in enumerate(all_items[:4]):
        # 排名数字
        draw.text((padding, current_y), f"{i+1}", font=font_rank, fill=(100, 100, 100))
        
        # 类型标签
        draw.rounded_rectangle([(padding+100, current_y+10), (padding+180, current_y+40)], 
                               radius=5, fill=(255, 200, 100))
        draw.text((padding+110, current_y+12), type_name, font=_get_font(16), fill=(20, 20, 20))
        
        # 标题
        title = item.get('SeriesName', item.get('ItemName', '未知'))[:16]
        draw.text((padding+100, current_y+50), title, font=font_name, fill=(255, 255, 255))
        
        # 播放数
        draw.text((padding+100, current_y+95), f"{item.get('C', 0)} 次播放", 
                 font=_get_font(18), fill=(150, 150, 150))
        
        current_y += 140
    
    return img


# 主函数 - 根据风格选择
def generate_poster_by_style(style='minimal'):
    """
    根据风格生成海报
    style: 'minimal' | 'cyber' | 'magazine'
    """
