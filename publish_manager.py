#!/usr/bin/env python3
import argparse, base64, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SELECTION=ROOT/"newsletter-selection.json"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--payload",required=True)
    a=p.parse_args()
    try:
        raw=base64.b64decode(a.payload.encode("ascii")).decode("utf-8")
        data=json.loads(raw)
    except Exception as exc:
        raise SystemExit(f"Invalid manager publish data: {exc}")
    items=data.get("items",[])
    if not isinstance(items,list):
        raise SystemExit("Publish data must contain an items list.")
    selected=[]
    custom=[]
    order=[]
    for x in items[:20]:
        if not isinstance(x,dict):
            continue
        if x.get("custom"):
            cid=str(x.get("link") or "").strip()
            body=str(x.get("message") or "").strip()
            if not cid or not body:
                continue
            custom.append({
                "id":cid,
                "title":str(x.get("title") or "From Media Jobs Report")[:160],
                "message":body[:5000],
                "url":str(x.get("url") or "")[:1000],
                "buttonText":str(x.get("buttonText") or "")[:60]
            })
            order.append({"kind":"custom","id":cid})
        else:
            link=str(x.get("link") or "").strip()
            if link.startswith("https://www.mediajobsreport.com/"):
                selected.append(link)
                order.append({"kind":"story","link":link})
    SELECTION.write_text(json.dumps({"selected":selected,"custom":custom,"order":order},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"Saved {len(selected)} stories and {len(custom)} newsletter-only messages.")

if __name__=="__main__":
    main()
