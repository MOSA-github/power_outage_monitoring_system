"""GitHub Actions generates the same public files in dummy and real modes."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys

from outage_data import FIELDS, JST, config_checked, dummy, real


def read_json(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def update(root, now=None, mode=None, interval=None, force=False):
    now=(now or datetime.now(timezone.utc)).astimezone(JST)
    config=config_checked(read_json(root/'config/monitor.json'))
    changed=mode is not None or interval is not None
    if mode is not None:config['mode']=mode
    if interval is not None:config['interval_minutes']=interval
    config_checked(config)
    status_file=root/'docs/data/status.json'
    previous=read_json(status_file) if status_file.exists() else {}
    same=previous.get('mode')==config['mode'] and previous.get('interval_minutes')==config['interval_minutes']
    stamp=previous.get('generated_at')
    if stamp and same and not changed and not force:
        due=datetime.fromisoformat(stamp)+timedelta(minutes=config['interval_minutes'])
        if now<due:return {'changed':False,'state':'not_due'}
    rows=dummy(config,now) if config['mode']=='dummy' else real(read_json(root/'data/real/latest.json'),config)
    generated=now.isoformat(timespec='seconds')
    status={'schema_version':1,'mode':config['mode'],'interval_minutes':config['interval_minutes'],
            'generated_at':generated,'next_update_at':(now+timedelta(minutes=config['interval_minutes'])).isoformat(timespec='seconds'),
            'state':'waiting_real' if config['mode']=='real' and not rows else 'ready','device_count':len(rows),
            'devices':config['devices']}
    # Validate everything before changing tracked configuration or artifacts.
    write_json(root/'config/monitor.json',config)
    write_json(root/'docs/data/latest.json',rows)
    output=io.StringIO();writer=csv.DictWriter(output,fieldnames=FIELDS,lineterminator='\n');writer.writeheader()
    writer.writerows([{k:('true' if v else 'false') if isinstance(v,bool) else v for k,v in row.items()} for row in rows])
    (root/'docs/data/latest.csv').write_text(output.getvalue(),encoding='utf-8',newline='\n')
    write_json(status_file,status)
    return {'changed':True,'state':status['state'],'mode':config['mode'],'device_count':len(rows)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',default='');parser.add_argument('--interval',default='')
    parser.add_argument('--force',action='store_true');args=parser.parse_args()
    try:
        interval=int(args.interval) if args.interval else None
        result=update(Path(__file__).resolve().parents[1],mode=args.mode or None,interval=interval,force=args.force)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as stream:stream.write('changed='+str(result['changed']).lower()+'\n')
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError):
        print('設定・データを確認してください。秘密値や元データは表示しません。',file=sys.stderr);return 1


if __name__=='__main__':sys.exit(main())
