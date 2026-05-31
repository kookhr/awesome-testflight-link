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

# Batch processing config
BATCH_SIZE = 50
BATCH_DELAY = 5  # seconds between batches

async def check_status(session, key, current_status, app_name=None, retry=5):
    """获取应用状态"""
    for i in range(retry):
        try:
            ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            async with session.get(f'/join/{key}', headers={'User-Agent': ua}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 404:
                    print(f"[info] {key} - 404 Deleted")
                    return (key, 'D')

                resp.raise_for_status()
                resp_html = await resp.text()

                # 检测状态
                if NO_PATTERN.search(resp_html):
                    return (key, 'N')
                elif FULL_PATTERN.search(resp_html):
                    return (key, 'F')
                elif "TestFlight" in resp_html:
                    return (key, 'Y')
                else:
                    print(f"[warn] {key} - Unexpected HTML content")
                    return (key, current_status)
        except asyncio.TimeoutError:
            wait = (2 ** i) + random.random()
            print(f"[warn] {key} - Timeout, retry {i+1}/{retry}, waiting {wait:.1f}s")
            await asyncio.sleep(wait)
        except Exception as e:
            wait = (2 ** i) + random.random()
            print(f"[warn] {key} - {e}, retry {i+1}/{retry}, waiting {wait:.1f}s")
            await asyncio.sleep(wait)

    print(f"[error] Failed to get status for {key} after {retry} retries")
    return (key, current_status)

async def update_all_links(links_data):
    """更新所有链接的状态（分批处理，避免触发速率限制）"""
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

            # Delay between batches (skip after last batch)
            if batch_start + BATCH_SIZE < total:
                print(f"[info] Waiting {BATCH_DELAY}s before next batch...")
                await asyncio.sleep(BATCH_DELAY)

    updated_count = 0
    for link, status in all_results:
        if link not in all_links:
            continue

        link_info = all_links[link]

        if link_info.get('status') != status:
            link_info['status'] = status
            link_info['last_modify'] = TODAY
            updated_count += 1

    print(f"[info] Status updated: {updated_count}")

async def main():
    links_data = load_links()
    await update_all_links(links_data)

    save_links(links_data)

    # 直接生成 README
    renew_readme()

if __name__ == "__main__":
    asyncio.run(main())
