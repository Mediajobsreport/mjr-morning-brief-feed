#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from generate_feed import (
    SOURCE_FEED, AVAILABLE_ITEMS, fetch_feed, should_include, clean_text,
    parse_date, load_selection, save_available_items
)

def main():
    source_root=ET.fromstring(fetch_feed(SOURCE_FEED))
    channel=source_root.find("channel")
    if channel is None:
        raise RuntimeError("The source RSS feed does not contain a channel.")
    eligible=[]
    for item in channel.findall("item"):
        if not should_include(item):
            continue
        title=clean_text(item.findtext("title",""))
        link=item.findtext("link","").strip()
        if title and link:
            eligible.append((parse_date(item),item))
    eligible.sort(key=lambda x:x[0],reverse=True)
    save_available_items(eligible[:AVAILABLE_ITEMS],load_selection())
    print(f"Refreshed editorial pool with {min(len(eligible),AVAILABLE_ITEMS)} item(s) without publishing the live feed.")

if __name__=="__main__":
    main()
