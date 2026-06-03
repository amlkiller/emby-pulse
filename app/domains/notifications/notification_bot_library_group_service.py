import logging
from collections import defaultdict


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger


def set_dependency_providers(*, logger_provider=None):
    global _logger_provider

    if logger_provider is not None:
        _logger_provider = logger_provider


def process_library_group(daemon, items, wait_between_groups=None):
    groups = defaultdict(list)
    for item in items:
        itype = item.get("Type")
        if itype in ["Episode", "Season"] and item.get("SeriesId"):
            groups[str(item.get("SeriesId"))].append(item)
        elif itype == "Series":
            groups[str(item.get("Id"))].append(item)
        else:
            groups[str(item.get("Id"))].append(item)

    for group_id, group_items in groups.items():
        try:
            is_tv = any(x.get("Type") in ["Episode", "Season", "Series"] for x in group_items)
            if is_tv:
                fresh_episodes = daemon._check_fresh_episodes(group_id)
                if fresh_episodes:
                    daemon._push_episode_group(group_id, fresh_episodes)
                else:
                    series_item = next((x for x in group_items if x.get("Type") == "Series"), None)
                    if series_item:
                        daemon._push_single_item(series_item)
                    else:
                        episodes_only = [x for x in group_items if x.get("Type") == "Episode"]
                        if episodes_only:
                            daemon._push_episode_group(group_id, episodes_only)
            else:
                daemon._push_single_item(group_items[0])
            if wait_between_groups and wait_between_groups():
                return
        except Exception as e:
            _logger_provider().error(f"[入库通知] 处理失败: {e}")
