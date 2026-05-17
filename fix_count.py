with open('C:/Users/35956/Desktop/EmbyPulse-Pro/app/plugins/cover_generator/plugin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: preview - style2 only needs 1 image
old1 = '''if style == "style2":
                    images_data = get_random_library_thumbs(library_id, count=count)'''
new1 = '''if style == "style2":
                    images_data = get_random_library_thumbs(library_id, count=1)  # 斜线分割只需1张'''
content = content.replace(old1, new1)

# Fix 2: generate - style2 only needs 1 image
old2 = '''if style == "style2":
                        images_data = get_random_library_thumbs(library_id, count=image_count)'''
new2 = '''if style == "style2":
                        images_data = get_random_library_thumbs(library_id, count=1)  # 斜线分割只需1张'''
content = content.replace(old2, new2)

with open('C:/Users/35956/Desktop/EmbyPulse-Pro/app/plugins/cover_generator/plugin.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed style2 image count to 1')
