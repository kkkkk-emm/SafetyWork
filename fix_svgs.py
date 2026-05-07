import os, re

svg_dir = "C:/Users/86134/Desktop/Courses/NetworkSecurity/SafetyWork/projects/cc_bos_report_ppt169_20260502/svg_output"

for fn in sorted(os.listdir(svg_dir)):
    if not fn.endswith('.svg'):
        continue
    path = os.path.join(svg_dir, fn)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern 1: font-family=""Microsoft YaHei", "PingFang SC", Arial, sans-serif"
    # → font-family="Microsoft YaHei, PingFang SC, Arial, sans-serif"
    content = re.sub(
        r'font-family=""Microsoft YaHei", "PingFang SC", Arial, sans-serif"',
        'font-family="Microsoft YaHei, PingFang SC, Arial, sans-serif"',
        content
    )

    # Pattern 2: font-family="Georgia, SimSun, serif"  — already correct, no need to fix

    # Pattern 3: (Already fixed above)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Fixed: {fn}')

print('Done!')
