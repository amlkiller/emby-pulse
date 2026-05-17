import sys
sys.stdout.reconfigure(encoding='utf-8')

# 读取文件
with open('C:/Users/35956/Desktop/EmbyPulse-Pro/app/services/report_service.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 替换图片质量
text = text.replace("img.save(output, format='JPEG', quality=95)", 
                    "img.save(output, format='JPEG', quality=85, optimize=True)")

# 写回文件
with open('C:/Users/35956/Desktop/EmbyPulse-Pro/app/services/report_service.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Image quality optimized')
