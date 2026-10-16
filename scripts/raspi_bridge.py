"""Read an existing SwitchBot CSV; never publish its MAC addresses or room names."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

from monitor import read_json, write_json
from outage_data import config_checked, normalize, timestamp


def convert(csv_path,mapping,config):
    if not isinstance(mapping,dict) or not mapping:raise ValueError('対応表がありません')
    devices={item['id']:item for item in config['devices']}
    if any(not isinstance(mac,str) or ident not in devices for mac,ident in mapping.items()):raise ValueError('対応表が正しくありません')
    latest={}
    with csv_path.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            ident=mapping.get(row.get('mac_addr','').lower())
            if not ident:continue
            record=normalize(row,devices[ident],False)
            if ident not in latest or record['measured_at']>latest[ident]['measured_at']:latest[ident]=record
    return [latest[key] for key in sorted(latest)]


def run(root,csv_path,map_path,publish=False):
    config=config_checked(read_json(root/'config/monitor.json'))
    mapping=read_json(map_path)
    rows=convert(csv_path,{key.lower():value for key,value in mapping.items()},config)
    if not rows:raise ValueError('対象データがありません')
    destination=root/'data/real/latest.json'
    changed=not destination.exists() or read_json(destination)!=rows
    if changed:write_json(destination,rows)
    if publish:
        # Deploy key / credential helper is configured locally, not in this repo.
        subprocess.run(['git','-C',str(root),'add','--','data/real/latest.json'],check=True)
        diff=subprocess.run(['git','-C',str(root),'diff','--cached','--quiet','--','data/real/latest.json'],capture_output=True)
        if diff.returncode not in (0,1):raise ValueError('Git差分を確認できません')
        if diff.returncode==1:subprocess.run(['git','-C',str(root),'commit','-m','Update Raspberry Pi outage measurements','--','data/real/latest.json'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(root),'push','origin','main'],check=True,capture_output=True)
    return changed


def main():
    parser=argparse.ArgumentParser(description='既存SwitchBot CSVを公開用の安定IDへ変換')
    parser.add_argument('--csv',type=Path,required=True);parser.add_argument('--device-map',type=Path,required=True)
    parser.add_argument('--publish',action='store_true');parser.add_argument('--watch',action='store_true')
    parser.add_argument('--interval-seconds',type=int,default=60);args=parser.parse_args()
    if args.interval_seconds<30:parser.error('確認周期は30秒以上です')
    root=Path(__file__).resolve().parents[1]
    while True:
        try:
            if args.publish:subprocess.run(['git','-C',str(root),'pull','--ff-only'],check=True,capture_output=True)
            changed=run(root,args.csv,args.device_map,args.publish)
            print('実機データ更新' if changed else '変更なし',flush=True)
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):
            print('実機取込に失敗。CSV・対応表・Git接続を確認してください。',file=sys.stderr,flush=True)
            if not args.watch:return 1
        if not args.watch:return 0
        time.sleep(args.interval_seconds)


if __name__=='__main__':sys.exit(main())
