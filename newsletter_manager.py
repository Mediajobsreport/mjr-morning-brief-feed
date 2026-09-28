#!/usr/bin/env python3
import argparse, json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SELECTION=ROOT/"newsletter-selection.json"
AVAILABLE=ROOT/"available-items.json"

def load_selection():
    if SELECTION.exists():
        data=json.loads(SELECTION.read_text(encoding="utf-8"))
        return data.get("selected",[])
    return []

def save_selection(selected):
    SELECTION.write_text(json.dumps({"selected":selected},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def available():
    if not AVAILABLE.exists():
        return []
    return json.loads(AVAILABLE.read_text(encoding="utf-8")).get("items",[])

def resolve(value):
    value=(value or "").strip()
    if not value:
        raise SystemExit("Item URL or exact headline is required.")
    for item in available():
        if value==item.get("link") or value==item.get("title"):
            return item.get("link")
    if value.startswith("http"):
        return value
    raise SystemExit("Item not found in available-items.json.")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["include","exclude","up","down","clear","select_all","publish","refresh"])
    p.add_argument("--item",default="")
    a=p.parse_args()
    selected=load_selection()

    if a.action=="refresh":
        subprocess.run([sys.executable,str(ROOT/"generate_feed.py")],check=True)
        return
    if a.action=="publish":
        subprocess.run([sys.executable,str(ROOT/"generate_feed.py")],check=True)
        return
    if a.action=="clear":
        selected=[]
    elif a.action=="select_all":
        selected=[x["link"] for x in available()][:20]
    else:
        link=resolve(a.item)
        if a.action=="include":
            if link not in selected:
                selected.append(link)
        elif a.action=="exclude":
            selected=[x for x in selected if x!=link]
        elif a.action in ("up","down"):
            if link not in selected:
                raise SystemExit("Item is not currently selected.")
            i=selected.index(link)
            j=i-1 if a.action=="up" else i+1
            if 0<=j<len(selected):
                selected[i],selected[j]=selected[j],selected[i]
    save_selection(selected)
    print(f"{len(selected)} item(s) selected.")

if __name__=="__main__":
    main()
