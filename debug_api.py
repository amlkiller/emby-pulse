import sys
sys.path.insert(0, '.')
from app.core.media_adapter import media_api
import datetime

# 获取 admin_id
users = media_api.get('/Users', timeout=5).json()
admin_id = None
for u in users:
    if u.get('Policy', {}).get('IsAdministrator'):
        admin_id = u['Id']
        break
if not admin_id and users:
    admin_id = users[0]['Id']

print(f'Admin ID: {admin_id}')

# 获取媒体库
lib_res = media_api.get(f'/Users/{admin_id}/Views', timeout=10).json()
libraries = lib_res.get('Items', [])
print(f'媒体库数量: {len(libraries)}')
for lib in libraries:
    print(f'  - {lib.get("Name")}: {lib.get("Id")}')

# 测试第一个媒体库的分页查询
if libraries:
    lib = libraries[0]
    lib_id = lib.get('Id')
    
    # 第一页
    params = {
        'ParentId': lib_id,
        'SortBy': 'DateCreated',
        'SortOrder': 'Descending',
        'IncludeItemTypes': 'Movie,Series,Episode',
        'Recursive': 'true',
        'StartIndex': 0,
        'Limit': 500,
        'Fields': 'DateCreated'
    }
    res = media_api.get(f'/Users/{admin_id}/Items', params=params, timeout=20).json()
    items = res.get('Items', [])
    total = res.get('TotalRecordCount', 0)
    print(f'\n媒体库 "{lib.get("Name")}" :')
    print(f'  TotalRecordCount: {total}')
    print(f'  返回条数: {len(items)}')
    
    if items:
        print(f'  第一条: {items[0].get("Name")} - {items[0].get("DateCreated")}')
        print(f'  最后一条: {items[-1].get("Name")} - {items[-1].get("DateCreated")}')

# 测试全局查询（无 ParentId）
print('\n=== 测试全局查询（无 ParentId）===')
params_global = {
    'SortBy': 'DateCreated',
    'SortOrder': 'Descending',
    'IncludeItemTypes': 'Movie,Series,Episode',
    'Recursive': 'true',
    'StartIndex': 0,
    'Limit': 500,
    'Fields': 'DateCreated'
}
res_global = media_api.get(f'/Users/{admin_id}/Items', params=params_global, timeout=20).json()
items_global = res_global.get('Items', [])
total_global = res_global.get('TotalRecordCount', 0)
print(f'  TotalRecordCount: {total_global}')
print(f'  返回条数: {len(items_global)}')
