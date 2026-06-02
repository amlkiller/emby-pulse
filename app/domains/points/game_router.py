import datetime
import random

from fastapi import APIRouter, Request

from app.core.security_utils import safe_error_message
from app.domains.points import point_dao

router = APIRouter()
# ===================== 🎰 老虎机 API =====================

@router.get("/api/slot/usage")
def get_slot_usage(request: Request):
    """获取今日老虎机使用次数"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        return {"status": "success", "used_today": point_dao.count_today_point_logs(user['Id'], action='老虎机')}

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/slot/spin")
def slot_spin(request: Request):
    """老虎机抽奖"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        # 获取配置
        config = point_dao.get_point_config()

        # 检查是否启用
        if config.get('enable_slot') != '1':
            return {"status": "error", "message": "老虎机功能未启用"}
        
        # 解析配置
        cost = int(config.get('slot_cost', 10))
        daily_free = int(config.get('slot_daily_free', 3))
        max_per_day = int(config.get('slot_max_per_day', 20))
        triple_mult = int(config.get('slot_triple_multiplier', 10))
        double_mult = int(config.get('slot_double_multiplier', 2))
        special_mult = int(config.get('slot_special_multiplier', 50))
        win_rate_modifier = float(config.get('slot_win_rate_modifier', 1.0))  # 中奖概率调节 (0-1)
        
        # 获取今日使用次数（使用 SQLite 本地时间函数）
        used_today = point_dao.count_today_point_logs(user['Id'], action='老虎机')
        
        # 检查每日次数限制
        if used_today >= max_per_day:
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}

        # 获取用户积分
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0

        # 🔥 修复：当 daily_free = 0 时，永远不免费
        # 当 daily_free > 0 时，前 daily_free 次免费
        is_free = False
        if daily_free > 0 and used_today < daily_free:
            is_free = True
        
        # 检查积分（非免费时需要足够积分）
        if not is_free and current_points < cost:
            return {"status": "error", "message": f"积分不足（需要 {cost} 积分）"}
        
        # 解析图案配置
        symbols_text = config.get('slot_symbols', '🍒|20|false\n🍋|20|false\n🍊|15|false\n🍇|15|false\n💎|10|false\n7️⃣|10|true\n⭐|5|true\n🎰|5|true')
        symbols = []
        for line in symbols_text.split('\n'):
            if not line.strip():
                continue
            parts = line.split('|')
            if len(parts) >= 2:
                symbols.append({
                    'emoji': parts[0].strip(),
                    'weight': int(parts[1]) if parts[1].strip().isdigit() else 10,
                    'special': parts[2].strip().lower() == 'true' if len(parts) > 2 else False
                })
        
        if not symbols:
            symbols = [
                {'emoji': '🍒', 'weight': 20, 'special': False},
                {'emoji': '🍋', 'weight': 20, 'special': False},
                {'emoji': '🍊', 'weight': 15, 'special': False},
                {'emoji': '🍇', 'weight': 15, 'special': False},
                {'emoji': '💎', 'weight': 10, 'special': False},
                {'emoji': '7️⃣', 'weight': 10, 'special': True},
                {'emoji': '⭐', 'weight': 5, 'special': True},
                {'emoji': '🎰', 'weight': 5, 'special': True}
            ]
        
        # 随机选择三个图案（按权重）
        import random
        
        # 🔥 中奖概率调节：通过增加"不匹配"的概率来降低中奖率
        # win_rate_modifier = 1.0 时，正常随机
        # win_rate_modifier < 1.0 时，后两个图案有更高概率选择不同的图案
        def get_random_symbol():
            total_weight = sum(s['weight'] for s in symbols)
            r = random.uniform(0, total_weight)
            for s in symbols:
                r -= s['weight']
                if r <= 0:
                    return s
            return symbols[0]
        
        def get_different_symbol(exclude_emoji):
            """选择一个与 exclude_emoji 不同的图案"""
            different_symbols = [s for s in symbols if s['emoji'] != exclude_emoji]
            if not different_symbols:
                return get_random_symbol()
            total_weight = sum(s['weight'] for s in different_symbols)
            r = random.uniform(0, total_weight)
            for s in different_symbols:
                r -= s['weight']
                if r <= 0:
                    return s
            return different_symbols[0]
        
        # 第一个图案正常随机
        first = get_random_symbol()
        
        # 第二、三个图案根据 win_rate_modifier 决定是否尝试不匹配
        if win_rate_modifier < 1.0 and random.random() > win_rate_modifier:
            # 尝试选择不同的图案
            second = get_different_symbol(first['emoji'])
        else:
            second = get_random_symbol()
        
        if win_rate_modifier < 1.0 and random.random() > win_rate_modifier:
            # 尝试选择与前两个都不同的图案
            exclude_emojis = [first['emoji'], second['emoji']]
            different_symbols = [s for s in symbols if s['emoji'] not in exclude_emojis]
            if different_symbols:
                total_weight = sum(s['weight'] for s in different_symbols)
                r = random.uniform(0, total_weight)
                for s in different_symbols:
                    r -= s['weight']
                    if r <= 0:
                        third = s
                        break
                else:
                    third = different_symbols[0]
            else:
                third = get_random_symbol()
        else:
            third = get_random_symbol()
        
        result = [first, second, third]
        result_emojis = [r['emoji'] for r in result]
        
        # 计算奖励
        reward = 0
        win = False
        message = "再接再厉！"
        
        # 🔥 基准积分用于奖励计算（始终使用配置的 cost 作为基准）
        base_cost = cost
        
        # 检查是否三同
        if result[0]['emoji'] == result[1]['emoji'] == result[2]['emoji']:
            win = True
            multiplier = special_mult if result[0]['special'] else triple_mult
            reward = base_cost * multiplier
            message = f"🎉 三同大奖！{result[0]['emoji']} x3 获得 {reward} 积分！"
        # 检查是否两同
        elif result[0]['emoji'] == result[1]['emoji'] or result[1]['emoji'] == result[2]['emoji'] or result[0]['emoji'] == result[2]['emoji']:
            win = True
            # 找出相同的图案
            if result[0]['emoji'] == result[1]['emoji']:
                matched = result[0]
            elif result[1]['emoji'] == result[2]['emoji']:
                matched = result[1]
            else:
                matched = result[0]
            
            multiplier = special_mult if matched['special'] else double_mult
            reward = base_cost * multiplier
            message = f"✨ 两同小奖！{matched['emoji']} x2 获得 {reward} 积分！"
        else:
            message = f"未中奖，{result_emojis[0]} {result_emojis[1]} {result_emojis[2]}"
        
        # 扣除积分（如果不是免费）
        if not is_free:
            current_points -= cost
        
        # 增加积分（如果中奖）
        if win:
            current_points += reward
        
        # 记录日志
        action_desc = f"老虎机抽奖: {result_emojis[0]} {result_emojis[1]} {result_emojis[2]}"
        if win:
            action_desc += f" 获得 {reward} 积分"
        else:
            action_desc += " 未中奖"
        
        balance_change = reward - (0 if is_free else cost)
        log_amount = reward if win else (-cost if not is_free else 0)
        point_result = point_dao.apply_game_point_change(
            user['Id'],
            user['Name'],
            '老虎机',
            balance_change,
            log_amount=log_amount,
        )
        if point_result.get("status") != "success":
            return {"status": "error", "message": point_result.get("message", "积分更新失败")}
        current_points = point_result["points"]
        
        return {
            "status": "success",
            "result": result_emojis,
            "win": win,
            "reward": reward,
            "message": message,
            "new_points": current_points,
            "used_today": used_today + 1
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ===================== 🎫 刮刮乐 API =====================

# 存储当前用户的刮刮卡状态（简单实现，生产环境应该用 Redis 或数据库）
scratch_cards = {}

@router.post("/api/scratch/buy")
def buy_scratch_card(request: Request):
    """购买刮刮卡"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        config = point_dao.get_point_config()
        
        # 检查是否启用
        if config.get('enable_web_scratch') != '1':
            return {"status": "error", "message": "刮刮乐功能未启用"}
        
        # 解析配置
        cost = int(config.get('web_scratch_cost', 10))
        win_numbers_count = int(config.get('web_scratch_win_numbers', 3))
        grid_count = int(config.get('web_scratch_grid_count', 12))
        min_reward = int(config.get('web_scratch_min_reward', 5))
        max_reward = int(config.get('web_scratch_max_reward', 100))
        match_rate = float(config.get('web_scratch_match_rate', 20))
        max_per_day = int(config.get('web_scratch_max_per_day', 20))  # 🔥 每日次数限制
        
        # 🔥 检查今日使用次数（使用 SQLite 本地时间函数）
        used_today = point_dao.count_today_point_logs(user['Id'], action_like='刮刮乐%')
        
        if used_today >= max_per_day:
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}
        
        # 获取用户积分
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0
        
        # 检查积分
        if current_points < cost:
            return {"status": "error", "message": f"积分不足（需要 {cost} 积分）"}
        
        buy_result = point_dao.buy_scratch_card(user['Id'], user['Name'], cost)
        if buy_result.get("status") != "success":
            return {"status": "error", "message": buy_result.get("message", "积分更新失败")}
        current_points = buy_result["new_points"]
        
        # 生成中奖数字（随机 3 个不重复的数字 1-50）
        import random
        win_numbers = random.sample(range(1, 51), win_numbers_count)
        
        # 生成格子（每个格子有数字和积分，数字可重复）
        grid = []
        for i in range(grid_count):
            # 根据匹配概率决定这个格子是否匹配中奖数字
            if random.uniform(0, 100) < match_rate:
                # 匹配：从中奖数字中随机选一个
                num = random.choice(win_numbers)
                is_match = True
            else:
                # 不匹配：生成一个不在中奖数字中的数字
                available_nums = [n for n in range(1, 51) if n not in win_numbers]
                num = random.choice(available_nums) if available_nums else random.randint(1, 50)
                is_match = False
            
            # 每个格子都有积分值
            cell_reward = random.randint(min_reward, max_reward)
            
            grid.append({
                'number': num,
                'reward': cell_reward,      # 格子显示的积分
                'matched': is_match,         # 是否匹配中奖数字
                'revealed': False
            })
        
        # 存储刮刮卡状态
        scratch_cards[user['Id']] = {
            'win_numbers': win_numbers,
            'grid': grid,
            'created_at': datetime.datetime.now().isoformat()
        }
        
        # 调试：确保每个格子都有 reward
        for i, cell in enumerate(grid):
            if cell.get('reward', 0) == 0:
                grid[i]['reward'] = random.randint(min_reward, max_reward)
        
        return {
            "status": "success",
            "win_numbers": win_numbers,
            "grid": grid,
            "new_points": current_points
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


@router.post("/api/scratch/reveal")
async def reveal_scratch_cell(request: Request):
    """刮开格子"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        data = await request.json()
        cell_index = data.get('cell_index', 0)
        
        # 获取刮刮卡
        card = scratch_cards.get(user['Id'])
        if not card:
            return {"status": "error", "message": "请先购买刮刮卡"}
        
        if cell_index < 0 or cell_index >= len(card['grid']):
            return {"status": "error", "message": "无效的格子"}

        cell = card['grid'][cell_index]

        # 已刮开的格子不能重复领奖
        if cell.get('revealed'):
            return {"status": "error", "message": "该格子已刮开"}

        # 如果匹配，发放奖励
        if cell['matched'] and cell['reward'] > 0:
            reward_result = point_dao.reveal_scratch_reward(user['Id'], user['Name'], cell['reward'])
            if reward_result.get("status") != "success":
                return {"status": "error", "message": reward_result.get("message", "积分更新失败")}
            current_points = reward_result["new_points"]

            cell['revealed'] = True

            return {
                "status": "success",
                "number": cell['number'],
                "reward": cell['reward'],
                "matched": True,
                "new_points": current_points
            }
        else:
            cell['revealed'] = True

            # 未匹配也返回格子的积分值（只是不能获得）
            return {
                "status": "success",
                "number": cell['number'],
                "reward": cell['reward'],
                "matched": False,
                "new_points": None
            }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# 🎡 幸运转盘
wheel_usage = {}  # 用户使用次数缓存

@router.get("/api/wheel/usage")
async def get_wheel_usage(request: Request):
    """获取转盘今日使用次数"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    # 获取配置
    config = point_dao.get_point_config()
    max_per_day = int(config.get('wheel_max_per_day', 20))
    
    count = point_dao.count_today_point_logs(user['Id'], action='幸运转盘')
    
    return {
        "status": "success",
        "used_today": count,
        "max_per_day": max_per_day
    }

@router.post("/api/wheel/spin")
async def spin_wheel(request: Request):
    """转动转盘"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        # 获取配置
        config = point_dao.get_point_config()
        enabled = config.get('enable_wheel', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "转盘功能未启用"}
        
        cost = int(config.get('wheel_cost', 10))
        daily_free = int(config.get('wheel_daily_free', 3))
        max_per_day = int(config.get('wheel_max_per_day', 20))
        
        # 加载扇区配置
        sectors = []
        for i in range(1, 7):
            reward = int(config.get(f'wheel_reward_{i}', [50, 30, 20, 10, 5, 0][i-1]))
            weight = int(config.get(f'wheel_weight_{i}', [5, 10, 15, 20, 25, 25][i-1]))
            sectors.append({'reward': reward, 'weight': weight})
        
        used_today = point_dao.count_today_point_logs(user['Id'], action='幸运转盘')
        
        # 检查次数限制
        if used_today >= max_per_day:
            return {"status": "error", "message": "今日次数已用完"}
        
        # 获取当前积分
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0
        
        # 🔥 修复：当 daily_free = 0 时，永远不免费
        is_free = False
        if daily_free > 0 and used_today < daily_free:
            is_free = True
        
        # 扣除积分
        if not is_free:
            if current_points < cost:
                return {"status": "error", "message": "积分不足"}
            current_points -= cost


        # 根据权重随机选择扇区
        total_weight = sum(s['weight'] for s in sectors)
        rand_val = random.uniform(0, total_weight)
        cumulative = 0
        selected_sector = sectors[0]
        sector_index = 0
        for i, sector in enumerate(sectors):
            cumulative += sector['weight']
            if rand_val <= cumulative:
                selected_sector = sector
                sector_index = i
                break
        
        # 发放奖励
        reward = selected_sector['reward']
        if reward > 0:
            current_points += reward
        
        # 记录日志
        used_today += 1
        point_result = point_dao.apply_game_point_change(user['Id'], user['Name'], '幸运转盘', reward - (0 if is_free else cost))
        if point_result.get("status") != "success":
            return {"status": "error", "message": point_result.get("message", "积分更新失败")}
        current_points = point_result["points"]
        
        # 返回结果
        message = f"🎉 恭喜获得 {reward} 积分！" if reward > 0 else "😢 谢谢参与，再接再厉！"
        
        # 计算旋转角度：让目标扇区中心对准顶部指针
        # 扇区0在顶部，扇区1在右上，扇区2在右下，扇区3在底部，扇区4在左下，扇区5在左上
        # 要让扇区N对准顶部，需要逆时针旋转 N*60 度
        rotation_angle = sector_index * 60
        
        return {
            "status": "success",
            "reward": reward,
            "sector_index": sector_index,
            "rotation_angle": rotation_angle,  # 直接返回旋转角度
            "sectors": sectors,
            "message": message,
            "new_points": current_points,
            "used_today": used_today,
            "is_free": is_free
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# 🎲 猜数字
guess_games = {}  # 用户游戏状态缓存

@router.post("/api/guess/start")
async def start_guess_game(request: Request):
    """开始猜数字游戏"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        # 获取配置
        config = point_dao.get_point_config()
        enabled = config.get('enable_guess', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "猜数字功能未启用"}
        
        cost = int(config.get('guess_cost', 5))
        range_str = config.get('guess_range', '1-100')
        range_parts = range_str.split('-')
        min_num = int(range_parts[0]) if len(range_parts) > 0 else 1
        max_num = int(range_parts[1]) if len(range_parts) > 1 else 100
        max_per_day = int(config.get('guess_max_per_day', 20))  # 🔥 每日次数限制
        
        used_today = point_dao.count_today_point_logs(user['Id'], action_like='猜数字%')
        
        if used_today >= max_per_day:
            return {"status": "error", "message": f"今日次数已用完（{max_per_day}次/天）"}
        
        points_row = point_dao.get_user_points_row(user['Id'])
        current_points = points_row[0] if points_row else 0

        # 扣除积分
        if current_points < cost:
            return {"status": "error", "message": "积分不足"}

        start_result = point_dao.apply_game_point_change(user['Id'], user['Name'], '猜数字-开始', -cost, require_min_points=cost)
        if start_result.get("status") != "success":
            return {"status": "error", "message": start_result.get("message", "积分更新失败")}
        current_points = start_result["points"]
        
        # 生成目标数字
        target_number = random.randint(min_num, max_num)
        
        # 存储游戏状态
        guess_games[user['Id']] = {
            'target_number': target_number,
            'tries_left': int(config.get('guess_max_tries', 7)),
            'history': [],
            'created_at': datetime.datetime.now().isoformat()
        }
        
        return {
            "status": "success",
            "new_points": current_points
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/guess/submit")
async def submit_guess(request: Request):
    """提交猜测"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        data = await request.json()
        guess = int(data.get('guess', 0))
        
        # 获取游戏状态
        game = guess_games.get(user['Id'])
        if not game:
            return {"status": "error", "message": "请先开始游戏"}
        
        # 获取配置
        config = point_dao.get_point_config()
        base_reward = int(config.get('guess_base_reward', 50))
        multipliers = [
            float(config.get('guess_multiplier_1', 5)),
            float(config.get('guess_multiplier_2', 3)),
            float(config.get('guess_multiplier_3', 2)),
            1.5, 1.2, 1, 0.8
        ]
        
        # 更新游戏状态
        game['history'].append(guess)
        game['tries_left'] -= 1
        tries_used = len(game['history'])
        
        # 判断结果
        if guess == game['target_number']:
            # 猜对了
            multiplier = multipliers[min(tries_used - 1, len(multipliers) - 1)]
            reward = int(base_reward * multiplier)
            
            # 发放奖励
            reward_result = point_dao.apply_game_point_change(user['Id'], user['Name'], '猜数字-猜中', reward)
            if reward_result.get("status") != "success":
                return {"status": "error", "message": reward_result.get("message", "积分更新失败")}
            current_points = reward_result["points"]
            
            # 清理游戏状态
            del guess_games[user['Id']]
            
            return {
                "status": "success",
                "won": True,
                "reward": reward,
                "new_points": current_points,
                "tries_left": game['tries_left']
            }
        
        elif game['tries_left'] <= 0:
            # 次数用完，游戏结束
            current_pts = point_dao.get_user_points_balance(user['Id'])
            point_dao.insert_point_log(user['Id'], user['Name'], '猜数字-失败', 0, current_pts)
            
            answer = game['target_number']
            del guess_games[user['Id']]
            
            return {
                "status": "success",
                "game_over": True,
                "answer": answer,
                "tries_left": 0
            }
        
        else:
            # 继续游戏，给出提示
            hint = "大了！往小猜" if guess > game['target_number'] else "小了！往大猜"
            return {
                "status": "success",
                "won": False,
                "game_over": False,
                "hint": hint,
                "tries_left": game['tries_left']
            }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# 🎟️ 彩票
@router.get("/api/lottery/my_tickets")
async def get_my_lottery_tickets(request: Request):
    """获取我的彩票号"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        return {
            "status": "success",
            "tickets": point_dao.list_lottery_ticket_numbers(user['Id'], today)
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/lottery/buy")
async def buy_lottery(request: Request):
    """购买彩票"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}
    
    try:
        data = await request.json()
        count = int(data.get('count', 1))
        if count < 1:
            return {"status": "error", "message": "购买数量无效"}
        custom_number = data.get('custom_number')  # 自选号码
        
        # 获取配置
        config = point_dao.get_point_config()
        enabled = config.get('enable_lottery', '0') == '1'
        if not enabled:
            return {"status": "error", "message": "彩票功能未启用"}
        
        cost = int(config.get('lottery_cost', 100))
        max_per_day = int(config.get('lottery_max_per_day', 10))
        
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        # 生成彩票号
        import random
        tickets = []
        ticket_count = count
        
        # 如果有自选号码，第一张用自选号码
        if custom_number and len(custom_number) == 4 and custom_number.isdigit():
            tickets.append(custom_number)
            count -= 1
        
        # 剩余的随机生成
        for _ in range(count):
            ticket_number = str(random.randint(0, 9999)).zfill(4)
            tickets.append(ticket_number)

        result = point_dao.buy_lottery_tickets(user['Id'], user['Name'], ticket_count, cost, max_per_day, today, tickets)
        if result.get("status") != "success":
            return result
        
        return {
            "status": "success",
            "tickets": tickets,
            "today_tickets": result["today_tickets"],
            "new_points": result["new_points"]
        }

    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/lottery/pool")
async def api_user_lottery_pool(request: Request):
    """用户社区获取奖池信息"""
    try:
        user = request.session.get("req_user")
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        # 获取配置
        config = point_dao.get_point_config()
        draw_hour = int(config.get('lottery_draw_hour', 20))
        max_per_day = int(config.get('lottery_max_per_day', 10))
        
        # 检查今天是否已开奖
        today_drawn_row = point_dao.get_lottery_winning_numbers(today)
        
        if today_drawn_row and today_drawn_row["winning_numbers"]:
            # 今天已开奖，显示明天的奖池
            target_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            next_draw_time = f"明天 {(datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%m-%d')} {draw_hour}:00"
        else:
            target_date = today
            next_draw_time = f"今天 {datetime.datetime.now().strftime('%m-%d')} {draw_hour}:00"

        pool_info = point_dao.get_lottery_pool_info(user['Id'] if user else None, today, target_date)
        
        return {
            "status": "success",
            "data": {
                "today_pool": pool_info["today_pool"],
                "today_tickets": pool_info["today_tickets"],
                "user_today_tickets": pool_info["user_today_tickets"],
                "target_date": target_date,
                "next_draw_time": next_draw_time,
                "today_winning_number": pool_info["today_winning_number"],
                "my_winning_tickets": pool_info["my_winning_tickets"],
                "my_prize_total": pool_info["my_prize_total"],
                "is_drawn": pool_info["today_drawn"],
                "max_per_day": max_per_day
            }
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.get("/api/lottery/results")
async def get_lottery_results(request: Request):
    """获取开奖结果"""
    try:
        user = request.session.get("req_user")
        user_id = user['Id'] if user else None
        return {
            "status": "success",
            "results": point_dao.list_lottery_results(user_id)
        }
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

