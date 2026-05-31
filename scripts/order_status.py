#!/usr/bin/python
"""Generate README with apps sorted by status (Y first, then F, N, D)."""
from utils import TODAY, renew_readme, load_links, save_links

def main():
    links_data = load_links()
    all_links = links_data.get("_links", {})

    # Sort links by status priority: Y=0, F=1, N=2, D=3, then alphabetically
    status_priority = {'Y': 0, 'F': 1, 'N': 2, 'D': 3}
    sorted_links = dict(sorted(
        all_links.items(),
        key=lambda x: (status_priority.get(x[1].get('status', 'N'), 9), x[1].get('app_name', '').lower())
    ))
    links_data["_links"] = sorted_links

    save_links(links_data)
    print("[info] Regenerating README with status-ordered links...")
    renew_readme()
    print("[info] Done!")

if __name__ == "__main__":
    main()
