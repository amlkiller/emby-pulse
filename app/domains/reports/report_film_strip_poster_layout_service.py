import io
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.domains.reports.report_assets import HAS_PIL

if HAS_PIL:
    from PIL import Image, ImageDraw


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger


def set_dependency_providers(logger_provider=None):
    global _logger_provider

    if logger_provider is not None:
        _logger_provider = logger_provider


def _get_val(item, key, default=None):
    try:
        return item[key] if key in item.keys() else default
    except:
        return item.get(key, default) if hasattr(item, 'get') else default


def draw_film_strip_layout(
    tv_list,
    movie_list,
    pc,
    theme_config,
    slogan,
    poster_provider,
    font_provider,
    default_font_provider,
):
    """Render the film-strip daily poster layout."""
    if not HAS_PIL:
        return None

    colors = theme_config['colors']
    bg_config = theme_config['background']
    bg_colors = bg_config['colors']
    decorations = theme_config.get('decorations', [])

    W = 1080
    padding = 60

    try:
        font_title = font_provider(72)
        font_subtitle = font_provider(22)
        font_date = font_provider(36)
        font_weekday = font_provider(28)
        font_section_cn = font_provider(36)
        font_section_en = font_provider(18)
        font_rank = font_provider(48)
        font_name = font_provider(24)
        font_count = font_provider(18)
        font_watermark = font_provider(20)
    except:
        font_title = font_subtitle = font_date = font_weekday = font_section_cn = font_section_en = font_rank = font_name = font_count = font_watermark = default_font_provider()

    header_h = 200
    section_h = 380
    footer_h = 60

    num_sections = (1 if tv_list else 0) + (1 if movie_list else 0)
    H = header_h + num_sections * section_h + footer_h + 40

    bg_config = theme_config['background']
    bg_colors = bg_config['colors']

    img = Image.new('RGB', (W, H), bg_colors[0])
    draw = ImageDraw.Draw(img)

    for y in range(H):
        ratio = y / H
        r = int(bg_colors[0][0] + ratio * (bg_colors[1][0] - bg_colors[0][0]))
        g = int(bg_colors[0][1] + ratio * (bg_colors[1][1] - bg_colors[0][1]))
        b = int(bg_colors[0][2] + ratio * (bg_colors[1][2] - bg_colors[0][2]))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    decorations = theme_config.get('decorations', [])

    if 'film_holes' in decorations:
        hole_w, hole_h = 12, 18
        for i in range(0, H, 35):
            draw.rounded_rectangle(
                [(15, i + 8), (15 + hole_w, i + 8 + hole_h)],
                radius=3,
                fill=colors['shadow'],
                outline=colors['divider'],
            )
            draw.rounded_rectangle(
                [(W - 15 - hole_w, i + 8), (W - 15, i + 8 + hole_h)],
                radius=3,
                fill=colors['shadow'],
                outline=colors['divider'],
            )

    if 'spotlight' in decorations:
        for r in range(500, 0, -5):
            draw.ellipse(
                [(-150, -250), (r * 2 - 150, r * 2 - 250)],
                fill=(bg_colors[1][0] + 20, bg_colors[1][1] + 15, bg_colors[1][2] + 25),
            )
        for r in range(400, 0, -4):
            draw.ellipse(
                [(W - 100, -200), (W + r * 2 - 100, r * 2 - 200)],
                fill=(bg_colors[1][0] + 15, bg_colors[1][1] + 10, bg_colors[1][2] + 20),
            )

    if 'bottom_glow' in decorations:
        for r in range(300, 0, -4):
            draw.ellipse(
                [(W // 2 - r, H - 100), (W // 2 + r, H + r)],
                fill=(bg_colors[1][0] + 5, bg_colors[1][1] + 3, bg_colors[1][2] + 8),
            )

    effects = theme_config.get('effects', {})

    if 'neon_grid' in decorations:
        grid_color = effects.get('grid_color', (80, 40, 120))
        for x in range(0, W, 80):
            draw.line([(x, 0), (x, H)], fill=grid_color, width=1)
        for y in range(0, H, 80):
            draw.line([(0, y), (W, y)], fill=grid_color, width=1)

    if 'sun_glow' in decorations:
        sun_y = effects.get('sun_y', 100)
        glow_color = effects.get('glow_color', (255, 150, 50))
        for r in range(200, 0, -5):
            opacity = r / 200
            draw.ellipse(
                [(W // 2 - r, sun_y - r), (W // 2 + r, sun_y + r)],
                fill=(int(glow_color[0] * opacity), int(glow_color[1] * opacity), int(glow_color[2] * opacity)),
            )

    if 'wave_lines' in decorations:
        wave_color = effects.get('wave_color', (30, 80, 120))
        for i in range(5):
            wave_y = H - 50 - i * 20
            for x in range(0, W, 10):
                y_offset = int(math.sin(x * 0.05 + i) * 8)
                draw.line([(x, wave_y + y_offset), (x + 10, wave_y + y_offset)], fill=wave_color, width=2)

    current_y = 50

    draw.text((padding, current_y), pc['title'], font=font_title, fill=colors['title'])
    current_y += 85

    date_text = pc['date_label']
    weekday_text = pc['weekday']
    draw.text((padding, current_y), date_text, font=font_date, fill=colors['date'])
    draw.text((padding + 320, current_y + 6), weekday_text, font=font_weekday, fill=colors['weekday'])

    draw.text((W - padding - 300, 60), pc['subtitle'], font=font_subtitle, fill=(120, 125, 140))
    draw.text((W - padding - 260, 90), slogan, font=font_count, fill=(100, 105, 120))

    current_y += 55
    draw.line([(padding, current_y), (W - padding, current_y)], fill=(60, 65, 80), width=2)
    current_y += 30

    tv_pattern = re.compile(r' - [sS]\d|第.+[集期]|EP?\d', re.IGNORECASE)

    def draw_rank_section(cn_title, en_title, items, y_start):
        y = y_start

        draw.text((padding, y), cn_title, font=font_section_cn, fill=colors['section_title'])
        en_bbox = draw.textbbox((0, 0), en_title, font=font_section_en)
        en_w = en_bbox[2] - en_bbox[0]
        draw.text((W - padding - en_w, y + 10), en_title, font=font_section_en, fill=colors['section_en'])
        y += 60

        poster_w, poster_h = 170, 240
        gap = 15
        total_width = 5 * poster_w + 4 * gap
        start_x = (W - total_width) // 2

        offsets = [0, 12, -8, 10, -5]

        def fetch_poster_for_item(idx, item):
            item_id = _get_val(item, 'ItemId')
            item_name = _get_val(item, 'ItemName', '')
            is_tv = "剧集" in cn_title and tv_pattern.search(item_name)
            poster = poster_provider(item_id, item_name, poster_w, poster_h, is_tv=is_tv)
            return idx, poster

        posters = {}
        items_to_process = items[:5]
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_poster_for_item, i, item) for i, item in enumerate(items_to_process)]
            for future in as_completed(futures, timeout=30):
                try:
                    idx, poster = future.result()
                    posters[idx] = poster
                except Exception as e:
                    _logger_provider().warning(f"[海报生成] 封面获取失败: {e}")

        poster_radius = colors.get('poster_radius', 12)

        for i, item in enumerate(items[:5]):
            poster = posters.get(i)

            x = start_x + i * (poster_w + gap)
            poster_y = y + offsets[i]

            shadow_offset = 6
            for s in range(3):
                draw.rounded_rectangle(
                    [
                        (x + shadow_offset + s, poster_y + shadow_offset + s),
                        (x + poster_w + shadow_offset - s, poster_y + poster_h + shadow_offset - s),
                    ],
                    radius=poster_radius,
                    fill=colors['shadow'],
                )

            if poster:
                mask = Image.new('L', (poster_w, poster_h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([(0, 0), (poster_w, poster_h)], radius=poster_radius, fill=255)

                resized = poster.resize((poster_w, poster_h), Image.LANCZOS)
                rounded = Image.new('RGBA', (poster_w, poster_h), (0, 0, 0, 0))
                rounded.paste(resized, (0, 0))
                rounded.putalpha(mask)

                img.paste(rounded.convert('RGB'), (x, poster_y), rounded.split()[3])
            else:
                placeholder_bg = colors['placeholder_bg']
                for py in range(poster_h):
                    ratio = py / poster_h
                    r = int(placeholder_bg[0][0] + ratio * (placeholder_bg[1][0] - placeholder_bg[0][0]))
                    g = int(placeholder_bg[0][1] + ratio * (placeholder_bg[1][1] - placeholder_bg[0][1]))
                    b = int(placeholder_bg[0][2] + ratio * (placeholder_bg[1][2] - placeholder_bg[0][2]))
                    draw.line([(x, poster_y + py), (x + poster_w, poster_y + py)], fill=(r, g, b))
                draw.rounded_rectangle(
                    [(x, poster_y), (x + poster_w, poster_y + poster_h)],
                    radius=poster_radius,
                    outline=colors['divider'],
                    width=1,
                )
                draw.text(
                    (x + poster_w // 2 - 36, poster_y + poster_h // 2),
                    "暂无封面",
                    font=font_count,
                    fill=colors['placeholder_text'],
                )

            rank_text = str(i + 1)
            rank_x = x + 10
            rank_y = poster_y + 10

            if i == 0:
                rank_color = colors['rank_1']
            elif i == 1:
                rank_color = colors['rank_2']
            elif i == 2:
                rank_color = colors['rank_3']
            else:
                rank_color = colors['rank_other']

            rank_size = 50
            draw.ellipse([(rank_x, rank_y), (rank_x + rank_size, rank_y + rank_size)], fill=colors['rank_bg'])
            draw.ellipse(
                [(rank_x, rank_y), (rank_x + rank_size, rank_y + rank_size)],
                outline=rank_color,
                width=3,
            )

            rank_bbox = draw.textbbox((0, 0), rank_text, font=font_rank)
            rank_w = rank_bbox[2] - rank_bbox[0]
            rank_h = rank_bbox[3] - rank_bbox[1]
            draw.text(
                (rank_x + (rank_size - rank_w) // 2, rank_y + (rank_size - rank_h) // 2 - 5),
                rank_text,
                font=font_rank,
                fill=rank_color,
            )

            name_y = poster_y + poster_h + 15
            name_text = _get_val(item, 'SeriesName') or _get_val(item, 'ItemName') or '未知'
            if len(name_text) > 8:
                name_text = name_text[:8] + '...'

            name_bbox = draw.textbbox((0, 0), name_text, font=font_name)
            name_w = name_bbox[2] - name_bbox[0]
            name_x = x + (poster_w - name_w) // 2
            draw.text((name_x, name_y), name_text, font=font_name, fill=colors['name'])

            duration = _get_val(item, 'Duration') or 0
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            if hours > 0:
                duration_text = f"{hours}h{minutes}m"
            else:
                duration_text = f"{minutes}分钟"
            count_bbox = draw.textbbox((0, 0), duration_text, font=font_count)
            count_w = count_bbox[2] - count_bbox[0]
            count_x = x + (poster_w - count_w) // 2
            draw.text((count_x, name_y + 32), duration_text, font=font_count, fill=colors['duration'])

        return y + poster_h + max(offsets) + 70

    if tv_list:
        current_y = draw_rank_section("热门剧集 TOP 5", "TV SHOWS TOP 5", tv_list, current_y)

    if movie_list:
        current_y = draw_rank_section("热门电影 TOP 5", "MOVIES TOP 5", movie_list, current_y)

    footer_y = current_y + 10
    draw.line([(padding, footer_y), (W - padding, footer_y)], fill=colors['divider'], width=1)

    watermark_text = "By Emby Pulse"
    bbox = draw.textbbox((0, 0), watermark_text, font=font_watermark)
    watermark_w = bbox[2] - bbox[0]
    draw.text(((W - watermark_w) // 2, footer_y + 15), watermark_text, font=font_watermark, fill=colors['watermark'])

    output = io.BytesIO()
    img.save(output, format='JPEG', quality=85, optimize=True)
    output.seek(0)
    return output
