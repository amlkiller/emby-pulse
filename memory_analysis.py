"""
内存分析脚本 - 检查 EmbyPulse-Pro 的内存使用情况
"""
import sys
import gc
import tracemalloc
import os
import threading
from collections import defaultdict

def analyze_memory():
    """分析内存使用情况"""
    print("=" * 60)
    print("EmbyPulse-Pro 内存分析")
    print("=" * 60)
    
    # 1. 检查全局缓存
    print("\n[1] 全局缓存检查:")
    
    try:
        from app.utils.ip_location import _ip_cache
        print(f"  - IP 缓存 (_ip_cache): {len(_ip_cache)} 条")
    except:
        print("  - IP 缓存: 无法访问")
    
    try:
        from app.routers.proxy import smart_image_cache, IMAGE_CACHE_DIR
        print(f"  - 智能图片缓存: {len(smart_image_cache)} 条")
        if os.path.exists(IMAGE_CACHE_DIR):
            file_count = 0
            total_bytes = 0
            for name in os.listdir(IMAGE_CACHE_DIR):
                path = os.path.join(IMAGE_CACHE_DIR, name)
                if os.path.isfile(path):
                    file_count += 1
                    total_bytes += os.path.getsize(path)
            print(f"  - 图片磁盘缓存: {file_count} 个文件, {total_bytes / 1024 / 1024:.2f} MB")
    except:
        print("  - 智能图片缓存: 无法访问")
    
    try:
        from app.routers.media_request import _community_cache
        print(f"  - 社区缓存 (_community_cache): {len(_community_cache)} 条")
    except:
        print("  - 社区缓存: 无法访问")

    try:
        from app.routers.stats import _dashboard_cache
        print(f"  - 仪表盘缓存: {'已缓存' if _dashboard_cache.get('data') else '未缓存'}")
    except:
        print("  - 仪表盘缓存: 无法访问")

    try:
        from app.core.database import get_query_perf_stats
        perf = get_query_perf_stats()
        print(f"  - 慢查询统计: {perf.get('slow')} 条, 大结果集: {perf.get('large_result')} 次")
    except:
        print("  - 查询统计: 无法访问")
    
    try:
        from app.plugins.media_search.plugin import _search_cache, _tmdb_cache
        print(f"  - 搜索缓存 (_search_cache): {len(_search_cache)} 条")
        print(f"  - TMDB 缓存 (_tmdb_cache): {len(_tmdb_cache)} 条")
    except:
        print("  - 搜索/TMDB 缓存: 无法访问")
    
    try:
        from app.plugins.offline.plugin import _transfer_cache, _offline_cache
        print(f"  - 离线缓存 (_transfer_cache): {len(_transfer_cache)} 条")
        print(f"  - 离线下载缓存 (_offline_cache): {len(_offline_cache)} 条")
    except:
        print("  - 离线缓存: 无法访问")
    
    # 2. 检查 bot_service 缓存
    print("\n[2] Bot Service 缓存检查:")
    try:
        from app.services.bot_service import bot_service
        if bot_service:
            print(f"  - user_cache: {len(bot_service.user_cache)} 条")
            print(f"  - ip_cache: {len(bot_service.ip_cache)} 条")
            print(f"  - delete_cache: {len(bot_service.delete_cache)} 条")
            print(f"  - library_queue: {len(bot_service.library_queue)} 条")
    except Exception as e:
        print(f"  - Bot Service 缓存: 无法访问 ({e})")

    print("\n[2.5] 线程检查:")
    print(f"  - Python 活跃线程: {threading.active_count()} 个")
    for t in threading.enumerate()[:20]:
        print(f"  - {t.name}")
    
    # 3. 检查对象数量
    print("\n[3] 对象统计 (前 20):")
    gc.collect()
    type_counts = defaultdict(int)
    for obj in gc.get_objects():
        type_counts[type(obj).__name__] += 1
    
    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:20]
    for type_name, count in sorted_types:
        print(f"  - {type_name}: {count}")
    
    # 4. 内存使用估计
    print("\n[4] 内存使用估计:")
    total_size = 0
    for obj in gc.get_objects():
        try:
            total_size += sys.getsizeof(obj)
        except:
            pass
    print(f"  - 估计总内存: {total_size / 1024 / 1024:.2f} MB")
    
    print("\n" + "=" * 60)
    print("分析完成")
    print("=" * 60)

if __name__ == "__main__":
    analyze_memory()
