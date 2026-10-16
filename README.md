# 停電監視（SwitchBot）

ダミーデータを定期更新し、Raspberry Pi復旧後は実機データへ切り替えるプロトタイプです。停電を確定する装置や生命維持用途の警報システムではありません。

## 使う

1. [公開ページ](https://mosa-github.github.io/power_outage_monitoring_system/)を開く。
2. 「更新設定」→ 既存MOSAdemy管理者でログイン。
3. ダミー／実機と更新周期（5〜1440分）を選択 →「設定を反映」。即時更新は「今すぐ更新」。

初期値はダミー・5分・2ポイント。ページを閉じてもActionsが更新します。画面の1分ごとのJSON確認と、データ自体の生成周期は別です。日時は日本時間・24時間表示。設定反映中はボタンを無効化し、完了・失敗はActionsリンクで確認します。

ダミーの状態は固定です。`switchbot-001`は停電想定（`OFFLINE`）、`switchbot-002`は通電（`NORMAL`）。通電側の消費電力は31.5〜33.5 W、両方の電波強度は基準値から±2 dBmの範囲で変動します。停電側は既存の欠損ルールに従い`value`・`switch_on`をnullにし、0Wの実測値とは区別します。更新や周期変更で`power_state`は変わりません。実機モードの判定は変更しません。

GitHub Actionsのscheduleは遅延・未実行があり得ます。[公式仕様](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。既存data-server側の1分確認タイマーでも期限到達時に同じ`monitor.yml`を起動し、生成・検証・公開処理はActionsに一本化します。指定時刻ちょうどの更新を保証するものではありません。

## データURL

- 最新JSON: <https://mosa-github.github.io/power_outage_monitoring_system/data/latest.json>
- 最新CSV: <https://mosa-github.github.io/power_outage_monitoring_system/data/latest.csv>
- 更新状態: <https://mosa-github.github.io/power_outage_monitoring_system/data/status.json>

`config/monitor.json`がモード・周期・公開ポイントIDの正本。`docs/data/`は生成物で、ActionsのPages artifact `docs/`が上記URLへ対応します。実機モードの受信元は`data/real/latest.json`。ダミー／実機を切り替えても利用URLは変わりません。

JSONは配列。各行は`sensor_id,name,type,value,unit,status,power_state,switch_on,ble_rssi,node_rssi,is_demo,measured_at`。`type`は`outage`、単位はW、電波強度はdBm。`is_demo:true`は検証用で実測値ではありません。`OFFLINE`/`UNKNOWN`は値とスイッチをnullにし、過去の電力を再利用しません。0Wは欠損と区別します。

`power_state`: NORMAL（通電・稼働）、0W_ALERT（機器停止）、SWITCH_OFF、OFFLINE（停電・通信途絶の疑い）、BLE_WEAK、NODE_WEAK、UNKNOWN。80秒の通信監視・40秒のRSSIホールドは既存Raspberry Pi側の責務です。公開ファイルの更新遅延を停電と判定しません。

## MOSAdemyデータ管理と接続

センサ種別「停電感知（SwitchBot）」→ JSON（URL取得）→ 上記最新JSONを指定。外部IDフィールドは`sensor_id`、外部センサIDは例`switchbot-001`、値`value`、時刻`measured_at`、停電状態`power_state`。その他は同名フィールド。内部台帳IDは変更せず、実機移行後も同じ外部IDを使います。取得ホストは既存の許可リストで承認。公開する場合は従来どおり公開承認・公開同期が必要です。施設名・座標は既存管理DBの施設マスターを使い、このリポジトリへ複製しません。

## 実機へ切り替える

1. Raspberry Piでこのリポジトリをclone。既存`raspi_power_checker.py`等のCSV記録を継続。
2. Pi上だけに`devices.local.json`を用意。例（架空MAC）:

```json
{"aa:bb:cc:dd:ee:ff":"switchbot-001"}
```

3. Python 3.10以上で変換を確認:

```bash
python3 scripts/raspi_bridge.py --csv /path/to/log.csv --device-map /path/to/devices.local.json
```

4. GitHubへの書込は、このリポジトリ専用の書込可能なSSH deploy key等をPiに設定。鍵をGitに入れない。送信開始:

```bash
python3 scripts/raspi_bridge.py --csv /path/to/log.csv --device-map /path/to/devices.local.json --publish --watch --interval-seconds 60
```

5. 実機データの到着を確認して、更新設定を「実機」へ変更。未着時は「実機データ待ち」となり、ダミーに自動復帰しません。

CSVは既存の`time,id,room,mac_addr,status,power,ble_rssi,node_rssi`を使用し、`power_w`・`power[W]`も対応。オフセットなしのtimeは日本時間。MAC・病院ID・部屋名を公開データへコピーせず、ローカル対応表で安定IDへ置換します。最新行の計測時刻を保持し、毎回の公開時刻へ書き換えません。変更がないと新規commitしません。push失敗は次回再試行し、非fast-forwardは上書きせず停止します。

## 開発・手動実行

```bash
python -m unittest discover -s tests -v
python scripts/monitor.py --force
python -m http.server 8000 --directory docs
```

設定の手動代替はGitHubの Actions → **Update outage data and publish Pages** → Run workflow。`mode`はdummy/real、`interval_minutes`は分、`force`は即時更新。管理画面は既存Backendの`/admin/outage-monitor`、内部APIは`/api/v1/admin/outage-monitor`（admin/super_admin、CSRF、監査・重複抑制あり）。GitHub App鍵・installation tokenはサーバー内だけで使用し、公開ページ・GET応答へ出しません。
