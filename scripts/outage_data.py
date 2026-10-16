"""Public, credential-free SwitchBot data contract shared by demo and Pi input."""
from datetime import datetime, timedelta, timezone
import math
import re

JST = timezone(timedelta(hours=9))
STATES = ('NORMAL', '0W_ALERT', 'SWITCH_OFF', 'OFFLINE', 'BLE_WEAK', 'NODE_WEAK', 'UNKNOWN')
FIELDS = ('sensor_id','name','type','value','unit','status','power_state','switch_on','ble_rssi','node_rssi','is_demo','measured_at')


def timestamp(value):
    if not isinstance(value, str):raise ValueError('計測時刻がありません')
    try:stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise ValueError('計測時刻が正しくありません') from None
    if stamp.tzinfo is None:stamp = stamp.replace(tzinfo=JST)
    return stamp.astimezone(JST).isoformat(timespec='seconds')


def config_checked(config):
    if not isinstance(config,dict) or set(config)!={'schema_version','mode','interval_minutes','devices'}:raise ValueError('設定項目が正しくありません')
    if config['schema_version'] != 1 or config['mode'] not in ('dummy','real'):raise ValueError('動作モードが正しくありません')
    interval=config['interval_minutes']
    if type(interval) is not int or not 5<=interval<=1440:raise ValueError('更新周期は5〜1440分です')
    devices=config['devices']
    if not isinstance(devices,list) or not 1<=len(devices)<=100:raise ValueError('監視ポイントは1〜100件です')
    ids=set()
    for device in devices:
        if not isinstance(device,dict) or set(device)!={'id','name'}:raise ValueError('監視ポイントの項目が正しくありません')
        ident,name=device['id'],device['name']
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',ident) or ident in ids:raise ValueError('監視ポイントIDが正しくありません')
        if not isinstance(name,str) or not 1<=len(name)<=80:raise ValueError('表示名が正しくありません')
        ids.add(ident)
    return config


def _rssi(value):
    if value in (None,''):return None
    if isinstance(value,bool):raise ValueError('電波強度が正しくありません')
    try:number=float(value)
    except (ValueError,TypeError):raise ValueError('電波強度が正しくありません') from None
    if not math.isfinite(number) or not -127<=number<=0:raise ValueError('電波強度が範囲外です')
    return number


def normalize(record, device, demo=False):
    state=str(record.get('power_state') or record.get('status') or 'UNKNOWN').strip().upper()
    if state not in STATES:raise ValueError('停電感知状態が正しくありません')
    value=record.get('value',record.get('power_w',record.get('power',record.get('power[W]'))))
    if state in ('OFFLINE','UNKNOWN'):value,switch=None,None
    else:
        if isinstance(value,bool):raise ValueError('電力値が正しくありません')
        try:value=float(value)
        except (ValueError,TypeError):raise ValueError('電力値が正しくありません') from None
        if not math.isfinite(value) or value<0:raise ValueError('電力値が範囲外です')
        if state=='NORMAL' and value==0:raise ValueError('正常稼働は0Wではありません')
        if state in ('0W_ALERT','SWITCH_OFF') and value!=0:raise ValueError('0W状態に電力値があります')
        switch=state!='SWITCH_OFF'
    return {'sensor_id':device['id'],'name':device['name'],'type':'outage','value':value,'unit':'W',
            'status':'normal' if state=='NORMAL' else 'offline' if state in ('OFFLINE','UNKNOWN') else 'warning',
            'power_state':state,'switch_on':switch,'ble_rssi':_rssi(record.get('ble_rssi')),'node_rssi':_rssi(record.get('node_rssi')),
            'is_demo':demo,'measured_at':timestamp(record.get('measured_at') or record.get('time'))}


def dummy(config, now):
    slot=int(now.timestamp())//(config['interval_minutes']*60)
    rows=[]
    for index,device in enumerate(config['devices']):
        state=STATES[(slot+index*2)%6]
        value=0 if state in ('0W_ALERT','SWITCH_OFF') else round(18+index*5+(slot%17)/10,1)
        rows.append(normalize({'power_state':state,'value':value,'ble_rssi':-95 if state=='BLE_WEAK' else -55-index,
                               'node_rssi':-85 if state=='NODE_WEAK' else -60-index,'measured_at':now.isoformat()},device,True))
    return rows


def real(records,config):
    if not isinstance(records,list) or len(records)>100:raise ValueError('実機データは100件以内の配列です')
    devices={item['id']:item for item in config['devices']};seen=set();rows=[]
    for record in records:
        if not isinstance(record,dict) or set(record)-set(FIELDS):raise ValueError('実機データに未承認の項目があります')
        ident=record.get('sensor_id')
        if not isinstance(ident,str) or ident not in devices or ident in seen:raise ValueError('実機の監視ポイントIDが正しくありません')
        if record.get('is_demo') is not False:raise ValueError('実機データはis_demo:falseが必要です')
        seen.add(ident);rows.append(normalize(record,devices[ident],False))
    return rows
