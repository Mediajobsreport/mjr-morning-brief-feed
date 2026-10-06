#!/usr/bin/env python3
"""Track newsletter editions in Eastern time, including evening preparation."""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def manual_edition_date(now):
    day = now.date()
    if now.hour >= 12:
        day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def published_today(now):
    today = now.date().isoformat()
    for filename in ('last-manual-publish.json', 'last-automatic-publish.json'):
        try:
            data = json.loads(Path(filename).read_text())
        except (OSError, ValueError):
            continue
        if data.get('edition_date', data.get('date')) == today:
            return True
    return False


def main():
    now = datetime.now(ZoneInfo('America/New_York'))
    action = sys.argv[1]
    if action == 'check':
        published = published_today(now)
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('published=' + str(published).lower() + '\n')
        print('Edition already published for today:', published)
        return
    if action not in ('manual', 'automatic'):
        raise SystemExit('Expected check, manual, or automatic')
    edition = manual_edition_date(now) if action == 'manual' else now.date().isoformat()
    path = Path('last-' + action + '-publish.json')
    path.write_text(json.dumps({'date': now.date().isoformat(),
                               'edition_date': edition,
                               'published_at': now.isoformat()}, indent=2) + '\n')


if __name__ == '__main__':
    main()
