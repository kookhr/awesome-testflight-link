#!/usr/bin/python
import asyncio
import aiohttp
import re
import random
import html
from utils import TODAY, renew_readme, load_links, save_links

BASE_URL = "https://testflight.apple.com/"
FULL_PATTERN = re.compile(r"版本的测试员已满|This beta is full")
NO_PATTERN = re.compile(r"版本目前不接受任何新测试员|This beta isn't accepting any new testers right now")
APP_NAME_PATTERN = re.compile(r"Join the (.+?) beta - TestFlight - Apple")
APP_NAME_CH_PATTERN = re.compile(r'加入 Beta 版"(.+?)" - TestFlight - Apple')
OG_IMAGE_PATTERN = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')

# Batch processing config
BATCH_SIZE = 50
BATCH_DELAY = 5  # seconds between batches

def extract_icon_url(resp_html):
    """从 TestFlight 页面提取应用图标 URL"""
    match = OG_IMAGE_PATTERN.search(resp_html)
    if not match:
        return ''
    url = match.group(1)
    # 过滤掉默认占位图
    if 'testflight.apple.com/images/' in url:
        return ''
    # 将大图 URL 转换为 120x120 小图标 URL
    # 原始: /1920x1080ia-80.png
    # 目标: /120x120bb-80.png (更小，加载快)
    url = re.sub(r'/\d+x\d+[^/]*\.png', '/120x120bb-80.png', url)
    return url

def extract_app_name(resp_html):
    """从 TestFlight 页面提取应用名称"""
    match = APP_NAME_PATTERN.search(resp_html)
    if match:
        return html.unescape(match.group(1)).strip()
    match = APP_NAME_CH_PATTERN.search(resp_html)
    if match:
        return html.unescape(match.group(1)).strip()
    return ''

async def check_status(session, key, current_status, app_name=None, retry=5):
    """获取应用状态、图标和应用名"""
    icon_url = ''
    fetched_name = ''
    for i in range(retry):
        try:
            ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            async with session.get(f'/join/{key}', headers={'User-Agent': ua}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 404:
                    print(f"[info] {key} - 404 Deleted")
                    return (key, 'D', '', '')

                resp.raise_for_status()
                resp_html = await resp.text()

                # 提取图标和应用名
                icon_url = extract_icon_url(resp_html)
                fetched_name = extract_app_name(resp_html)

                # 检测状态
                if NO_PATTERN.search(resp_html):
                    return (key, 'N', icon_url, fetched_name)
                elif FULL_PATTERN.search(resp_html):
                    return (key, 'F', icon_url, fetched_name)
                elif "TestFlight" in resp_html:
                    return (key, 'Y', icon_url, fetched_name)
                else:
                    print(f"[warn] {key} - Unexpected HTML content")
                    return (key, current_status, icon_url, fetched_name)
        except asyncio.TimeoutError:
            wait = (2 ** i) + random.random()
            print(f"[warn] {key} - Timeout, retry {i+1}/{retry}, waiting {wait:.1f}s")
            await asyncio.sleep(wait)
        except Exception as e:
            wait = (2 ** i) + random.random()
            print(f"[warn] {key} - {e}, retry {i+1}/{retry}, waiting {wait:.1f}s")
            await asyncio.sleep(wait)

    print(f"[error] Failed to get status for {key} after {retry} retries")
    return (key, current_status, '', '')

async def update_all_links(links_data):
    """更新所有链接的状态、图标和应用名（分批处理）"""
    print(f"[info] Updating all links...")
    all_links = links_data.get("_links", {})
    links = list(all_links.keys())

    if not links:
        print("[warn] No links found")
        return

    total = len(links)
    all_results = []

    conn_config = aiohttp.TCPConnector(limit=5, limit_per_host=2)
    async with aiohttp.ClientSession(base_url=BASE_URL, connector=conn_config) as session:
        for batch_start in range(0, total, BATCH_SIZE):
            batch = links[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"[info] Processing batch {batch_num}/{total_batches} ({len(batch)} links)")

            tasks = [
                check_status(session, link, all_links[link].get('status', 'N'), all_links[link].get('app_name'))
                for link in batch
            ]
            results = await asyncio.gather(*tasks)
            all_results.extend(results)

            if batch_start + BATCH_SIZE < total:
                print(f"[info] Waiting {BATCH_DELAY}s before next batch...")
                await asyncio.sleep(BATCH_DELAY)

    status_updated = 0
    icon_updated = 0
    name_updated = 0
    for link, status, icon_url, fetched_name in all_results:
        if link not in all_links:
            continue

        link_info = all_links[link]

        if link_info.get('status') != status:
            link_info['status'] = status
            link_info['last_modify'] = TODAY
            status_updated += 1

        # 更新图标（只在有新图标且当前无图标时更新，避免覆盖）
        if icon_url and not link_info.get('icon_url'):
            link_info['icon_url'] = icon_url
            icon_updated += 1

        # 更新应用名（只在当前无名称或名称为空时更新）
        if fetched_name and not link_info.get('app_name'):
            link_info['app_name'] = fetched_name
            name_updated += 1

    print(f"[info] Status updated: {status_updated}, Icons added: {icon_updated}, Names added: {name_updated}")

async def main():
    links_data = load_links()
    await update_all_links(links_data)

    save_links(links_data)

    # 直接生成 README
    renew_readme()

if __name__ == "__main__":
    asyncio.run(main())
