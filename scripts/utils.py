import json
import datetime
from pathlib import Path
from collections import Counter

# Paths
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / "data"
LINKS_JSON = DATA_DIR / "links.json"
README_TEMPLATE_FILE = DATA_DIR / "README.template"
README_FILE = SCRIPT_DIR.parent / "README.md"

TODAY = datetime.datetime.now(datetime.UTC).date().strftime("%Y-%m-%d")

STATUS_INFO = {
    'Y': {'name': 'Available', 'description': 'Apps currently accepting new testers'},
    'F': {'name': 'Full', 'description': 'Apps that have reached their tester limit'},
    'N': {'name': 'No', 'description': 'Apps not currently accepting testers'},
    'D': {'name': 'Removed', 'description': 'Apps that have been removed from TestFlight'}
}

PLATFORM_NAMES = {
    'ios': 'iOS',
    'ipados': 'iPadOS',
    'macos': 'macOS',
    'tvos': 'tvOS',
}

def load_links():
    with open(LINKS_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_links(links):
    with open(LINKS_JSON, 'w', encoding='utf-8') as f:
        json.dump(links, f, indent=2, ensure_ascii=False)


def generate_stats_summary(links_data):
    """生成统计摘要，替代冗长的应用列表"""
    all_links = links_data.get("_links", {})

    # 按状态统计
    status_count = Counter(v.get('status', 'N') for v in all_links.values())

    # 按平台统计
    platform_status = {}  # {platform: {status: count}}
    for v in all_links.values():
        for t in v.get('tables', []):
            if t not in platform_status:
                platform_status[t] = Counter()
            platform_status[t][v.get('status', 'N')] += 1

    total = len(all_links)
    active = status_count.get('Y', 0)

    lines = [
        f"## 📈 Overview ({total} apps total, {active} currently accepting testers)\n",
        "",
        "| Platform | ✅ Available | ⚠️ Full | ❌ Closed | 🗑️ Removed | Total |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    # 按平台顺序输出
    for plat_key in ['ios', 'ipados', 'macos', 'tvos']:
        if plat_key not in platform_status:
            continue
        sc = platform_status[plat_key]
        plat_total = sum(sc.values())
        plat_name = PLATFORM_NAMES.get(plat_key, plat_key)
        lines.append(
            f"| {plat_name} | {sc.get('Y', 0)} | {sc.get('F', 0)} | {sc.get('N', 0)} | {sc.get('D', 0)} | {plat_total} |"
        )

    # 合计行
    lines.append(
        f"| **Total** | **{status_count.get('Y', 0)}** | **{status_count.get('F', 0)}** | **{status_count.get('N', 0)}** | **{status_count.get('D', 0)}** | **{total}** |"
    )
    lines.append("")

    return "\n".join(lines)


def generate_platform_section(table_name, links_data):
    """从 links.json 直接生成平台部分的 markdown 内容（保留用于 order_status 等场景）"""
    all_links = links_data.get("_links", {})

    table_links = {
        link_id: info for link_id, info in all_links.items()
        if table_name in info.get("tables", [])
    }

    if not table_links:
        return ""

    markdown = []

    for status_code in ['Y', 'F', 'N', 'D']:
        apps = sorted(
            [
                {
                    'app_name': info['app_name'],
                    'testflight_link': link_id,
                    'status': info['status'],
                    'last_modify': info['last_modify']
                }
                for link_id, info in table_links.items()
                if info['status'] == status_code
            ],
            key=lambda x: x['app_name'].lower()
        )

        if not apps:
            continue

        status_data = STATUS_INFO[status_code]
        app_count = len(apps)

        markdown.append(f"<details {'open' if status_code == 'Y' else ''}>\n")
        markdown.append(f"<summary><strong>{status_data['name']} ({app_count} app{'s' if app_count != 1 else ''})</strong> - {status_data['description']}</summary>\n\n")

        if status_code == 'Y':
            markdown.append(f"_✅ These {app_count} apps are currently accepting new testers! Click the links to join._\n\n")
        elif status_code == 'F':
            markdown.append(f"_⚠️ These {app_count} apps have reached their tester limit. Try checking back later._\n\n")

        markdown.append("| Name | TestFlight Link | Status | Last Updated |\n")
        markdown.append("| --- | --- | --- | --- |\n")

        for app in apps:
            full_link = f"https://testflight.apple.com/join/{app['testflight_link']}"
            markdown.append(f"| {app['app_name']} | [{full_link}]({full_link}) | {app['status']} | {app['last_modify']} |\n")

        markdown.append("\n</details>\n\n")

    return "".join(markdown)


def renew_readme():
    if not README_TEMPLATE_FILE.exists():
        print(f"Error: Template file {README_TEMPLATE_FILE} not found")
        return

    links_data = load_links()

    with open(README_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()

    content = template

    # 生成统计摘要
    stats_summary = generate_stats_summary(links_data)
    content = content.replace("#{STATS_SUMMARY}", stats_summary)

    # 兼容旧 template 的平台占位符（如果存在则生成完整列表）
    platform_map = {
        "iOS_APPS": ("ios", "## iOS App List\n\n"),
        "iPadOS_APPS": ("ipados", "## iPadOS App List\n\n"),
        "macOS_APPS": ("macos", "## macOS App List\n\n"),
        "tvOS_APPS": ("tvos", "## tvOS App List\n\n"),
    }

    for placeholder, (table_name, heading) in platform_map.items():
        tag = f"#{{{placeholder}}}"
        if tag in content:
            platform_content = generate_platform_section(table_name, links_data)
            if platform_content.strip():
                content = content.replace(tag, heading + platform_content)
            else:
                content = content.replace(tag, "")

    # 读取并插入 signup.md 文件内容
    signup_file = DATA_DIR / "signup.md"
    signup_tag = "#{SIGNUP_APPS}"
    if signup_tag in content:
        if signup_file.exists():
            try:
                with open(signup_file, 'r', encoding='utf-8') as f:
                    signup_content = f.read()
                content = content.replace(signup_tag, signup_content)
            except Exception as e:
                print(f"[warn] Failed to read signup.md: {e}")
                content = content.replace(signup_tag, "")
        else:
            content = content.replace(signup_tag, "")

    with open(README_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
