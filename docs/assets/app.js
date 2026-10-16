const states={NORMAL:'通電・稼働','0W_ALERT':'0W・機器停止',SWITCH_OFF:'スイッチOFF',OFFLINE:'停電・通信途絶の疑い',BLE_WEAK:'BLE電波弱',NODE_WEAK:'中継器電波弱',UNKNOWN:'未確認'};
const $=selector=>document.querySelector(selector);
function japanTime(value){if(!value)return '—';const date=new Date(value);return Number.isNaN(date.getTime())?'—':new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(date)}
function element(tag,text,style){const node=document.createElement(tag);node.textContent=text;if(style)node.className=style;return node}
function detail(label,value){const wrap=document.createElement('div');wrap.append(element('dt',label),element('dd',value));return wrap}
let loading=false;
const jsonUrl=new URL('data/latest.json',location.href);
$('#jsonUrl').textContent=jsonUrl.href;
$('#copyUrl').onclick=async()=>{try{await navigator.clipboard.writeText(jsonUrl.href);$('#copyResult').textContent='コピーしました'}catch{$('#copyResult').textContent='上のURLを選択してコピーしてください'}};
async function refresh(){
  if(loading)return;loading=true;$('#refresh').disabled=true;
  try{
    const stamp=Date.now();
    const read=async path=>{const url=new URL(path,location.href);url.searchParams.set('t',stamp);const response=await fetch(url,{cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer'});if(!response.ok)throw Error();return response.json()};
    const [status,rows]=await Promise.all([read('data/status.json'),read('data/latest.json')]);
    if(!['dummy','real'].includes(status.mode)||!Number.isInteger(status.interval_minutes)||status.interval_minutes<5||!Array.isArray(rows)||rows.some(row=>!row||row.type!=='outage'||typeof row.is_demo!=='boolean'||row.is_demo!==(status.mode==='dummy')||!states[row.power_state]))throw Error();
    const demo=status.mode==='dummy';$('#mode').textContent=demo?'ダミー':'実機';$('#modeBadge').textContent=demo?'検証用・ダミー':'実機モード';
    $('#interval').textContent=`${status.interval_minutes}分`;$('#generated').textContent=japanTime(status.generated_at);$('#nextUpdate').textContent=japanTime(status.next_update_at);
    const notice=$('#modeNotice');notice.className='notice'+(demo?'':' real');notice.textContent=demo?'検証用のダミーデータです。実機・実施設の状態を示しません。':status.state==='waiting_real'?'実機データ待ち。ダミーデータは表示しません。':'Raspberry Piから受信した実機データを表示しています。';
    const generated=new Date(status.generated_at).getTime();if(Number.isFinite(generated)&&Date.now()-generated>(status.interval_minutes*60+180)*1000){notice.className='notice error';notice.textContent+=' 更新が遅れています。自動更新の実行履歴を確認してください。'}
    $('#count').textContent=`${rows.length}件`;const cards=[];
    for(const row of rows){
      const card=element('article','',`device ${['normal','warning','offline'].includes(row.status)?row.status:'offline'}`);
      card.append(element('span',demo?'検証用・ダミー':'実機データ','chip'),element('h3',row.name||row.sensor_id),element('div',row.sensor_id,'id'),element('p',states[row.power_state],'state'));
      const absent=['OFFLINE','UNKNOWN'].includes(row.power_state),value=!absent&&typeof row.value==='number'&&Number.isFinite(row.value)?`${row.value.toLocaleString('ja-JP',{maximumFractionDigits:1})} W`:'欠損';
      card.append(element('p',`消費電力 ${value}`,'reading'));
      const list=document.createElement('dl');list.append(detail('スイッチ',absent||row.switch_on==null?'不明':row.switch_on?'ON':'OFF'),detail('電波強度',`BLE ${row.ble_rssi??'—'} / 中継 ${row.node_rssi??'—'} dBm`),detail('計測時刻（日本時間）',japanTime(row.measured_at)));card.append(list);
      const stale=new Date(row.measured_at).getTime();if(!Number.isFinite(stale)||Date.now()-stale>(status.interval_minutes*60+180)*1000)card.append(element('p','計測データが古い可能性があります','muted'));
      if(row.power_state==='OFFLINE')card.append(element('p','停電・機器故障・通信途絶は区別できません','muted'));cards.push(card);
    }
    $('#devices').replaceChildren(...(cards.length?cards:[element('p',demo?'データなし':'実機データ待ち')]));
    $('#refreshState').textContent=`公開JSONの確認時刻 ${japanTime(new Date().toISOString())} ／ データの値・生成時刻は上流の更新時だけ変わります`;
  }catch{$('#refreshState').textContent='公開データを取得できません。自動更新の実行履歴を確認してください。'}
  finally{loading=false;$('#refresh').disabled=false}
}
$('#refresh').onclick=refresh;refresh();setInterval(()=>{if(!document.hidden)refresh()},60000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
