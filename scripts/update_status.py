#!/usr/bin/python
import asyncio
import aiohttp
import re
import random
import html
import json
import os
from pathlib import Path
from utils import TODAY, renew_readme, load_links, save_links

BASE_URL = "https://testflight.apple.com/"
ITUNES_URL = "https://itunes.apple.com/search"
FULL_PATTERN = re.compile(r"版本的测试员已满|This beta is full")
NO_PATTERN = re.compile(r"版本目前不接受任何新测试员|This beta isn't accepting any new testers right now")
APP_NAME_PATTERN = re.compile(r"Join the (.+?) beta - TestFlight - Apple")
APP_NAME_CH_PATTERN = re.compile(r'加入 Beta 版"(.+?)" - TestFlight - Apple')
OG_IMAGE_PATTERN = re.compile(r'<meta\s+property="og:image"\s+content="([^"]+)"')

# Batch processing config
BATCH_SIZE = 50
BATCH_DELAY = 5  # seconds between batches
ITUNES_BATCH_SIZE = 20
ITUNES_BATCH_DELAY = 2  # seconds between iTunes batches

# Checkpoint file for resume after failure
CHECKPOINT_FILE = Path(__file__).parent.parent / "data" / ".update_checkpoint.json"


def extract_icon_url(resp_html):
    """从 TestFlight 页面提取应用图标 URL"""
    match = OG_IMAGE_PATTERN.search(resp_html)
    if not match:
        return ''
    url = match.group(1)
    if 'testflight.apple.com/images/' in url:
        return ''
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


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except Exception:
            pass
    return {"completed_keys": [], "results": []}


def save_checkpoint(cp):
    CHECKPOINT_FILE.write_text(json.dumps(cp, ensure_ascii=False))


def clear_checkpoint():
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


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

                icon_url = extract_icon_url(resp_html)
                fetched_name = extract_app_name(resp_html)

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


async def fetch_itunes_icon(session, app_name):
    """从 iTunes Search API 获取应用图标 URL"""
    if not app_name:
        return ''
    try:
        params = {'term': app_name, 'entity': 'software', 'limit': 1}
        async with session.get(ITUNES_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return ''
            data = await resp.json(content_type=None)
            if data.get('resultCount', 0) > 0:
                # Use 120x120 version of the icon
                icon = data['results'][0].get('artworkUrl60', '')
                if icon:
                    return icon.replace('/60x60bb.jpg', '/120x120bb-80.png').replace('/60x60bb-80.png', '/120x120bb-80.png')
    except Exception:
        pass
    return ''


async def update_all_links(links_data):
    """更新所有链接的状态、图标和应用名（分批处理 + 断点续传）"""
    print(f"[info] Updating all links...")
    all_links = links_data.get("_links", {})
    all_keys = list(all_links.keys())

    if not all_keys:
        print("[warn] No links found")
        return

    # Resume support
    cp = load_checkpoint()
    completed_set = set(cp["completed_keys"])
    all_results = cp["results"]

    remaining_keys = [k for k in all_keys if k not in completed_set]
    if completed_set:
        print(f"[info] Resuming from checkpoint: {len(completed_set)} completed, {len(remaining_keys)} remaining")

    total = len(remaining_keys)
    conn_config = aiohttp.TCPConnector(limit=5, limit_per_host=2)
    async with aiohttp.ClientSession(base_url=BASE_URL, connector=conn_config) as session:
        for batch_start in range(0, total, BATCH_SIZE):
            batch = remaining_keys[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
            print(f"[info] Processing batch {batch_num}/{total_batches} ({len(batch)} links)")

            tasks = [
                check_status(session, key, all_links[key].get('status', 'N'), all_links[key].get('app_name'))
                for key in batch
            ]
            results = await asyncio.gather(*tasks)
            all_results.extend(results)

            cp["completed_keys"].extend(batch)
            cp["results"] = all_results
            save_checkpoint(cp)

            if batch_start + BATCH_SIZE < total:
                print(f"[info] Waiting {BATCH_DELAY}s before next batch...")
                await asyncio.sleep(BATCH_DELAY)

    # Apply results to links_data
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

        if icon_url and link_info.get('icon_url') != icon_url:
            link_info['icon_url'] = icon_url
            icon_updated += 1

        if fetched_name and link_info.get('app_name') != fetched_name:
            link_info['app_name'] = fetched_name
            name_updated += 1

    print(f"[info] Status updated: {status_updated}, Icons updated: {icon_updated}, Names updated: {name_updated}")

    # Phase 2: Fill missing icon_url via iTunes Search API
    missing_icon_keys = [k for k, v in all_links.items() if not v.get('icon_url') and v.get('app_name')]
    if missing_icon_keys:
        print(f"[info] Filling {len(missing_icon_keys)} missing icons via iTunes Search API...")
        itunes_icon_updated = 0

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=3)) as itunes_session:
            for i in range(0, len(missing_icon_keys), ITUNES_BATCH_SIZE):
                batch = missing_icon_keys[i:i + ITUNES_BATCH_SIZE]
                tasks = [fetch_itunes_icon(itunes_session, all_links[k].get('app_name', '')) for k in batch]
                icons = await asyncio.gather(*tasks)

                for key, icon in zip(batch, icons):
                    if icon and not all_links[key].get('icon_url'):
                        all_links[key]['icon_url'] = icon
                        itunes_icon_updated += 1

                if i + ITUNES_BATCH_SIZE < len(missing_icon_keys):
                    await asyncio.sleep(ITUNES_BATCH_DELAY)

        print(f"[info] iTunes icons filled: {itunes_icon_updated}")

    clear_checkpoint()


async def main():
    links_data = load_links()
    await update_all_links(links_data)
    save_links(links_data)
    renew_readme()

if __name__ == "__main__":
    asyncio.run(main())
