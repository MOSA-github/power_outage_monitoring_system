import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from monitor import update,read_json,write_json
from outage_data import config_checked,dummy,normalize,real
from raspi_bridge import convert,run

NOW=datetime(2026,10,17,0,0,tzinfo=timezone.utc)
CONFIG={'schema_version':1,'mode':'dummy','interval_minutes':5,'devices':[{'id':'switchbot-001','name':'監視1'}]}


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        write_json(self.root/'config/monitor.json',copy.deepcopy(CONFIG));write_json(self.root/'data/real/latest.json',[])
    def tearDown(self):self.temp.cleanup()

    def test_all_six_dummy_states_have_explicit_demo_flag_and_japan_time(self):
        states=set()
        for index in range(6):
            row=dummy(CONFIG,NOW+timedelta(minutes=5*index))[0];states.add(row['power_state'])
            self.assertTrue(row['is_demo']);self.assertTrue(row['measured_at'].endswith('+09:00'));self.assertEqual(row['sensor_id'],'switchbot-001')
            if row['power_state']=='OFFLINE':self.assertIsNone(row['value']);self.assertIsNone(row['switch_on'])
        self.assertEqual(states,{'NORMAL','0W_ALERT','SWITCH_OFF','OFFLINE','BLE_WEAK','NODE_WEAK'})

    def test_interval_and_force_do_not_use_browser_activity(self):
        self.assertTrue(update(self.root,NOW)['changed'])
        self.assertNotIn(b'\r',(self.root/'docs/data/latest.csv').read_bytes())
        self.assertFalse(update(self.root,NOW+timedelta(minutes=4))['changed'])
        self.assertTrue(update(self.root,NOW+timedelta(minutes=5))['changed'])
        self.assertTrue(update(self.root,NOW+timedelta(minutes=6),force=True)['changed'])

    def test_custom_interval_and_settings_are_persistent(self):
        update(self.root,NOW,interval=7)
        self.assertEqual(read_json(self.root/'config/monitor.json')['interval_minutes'],7)
        self.assertFalse(update(self.root,NOW+timedelta(minutes=6))['changed'])
        self.assertTrue(update(self.root,NOW+timedelta(minutes=7))['changed'])

    def test_real_mode_with_no_pi_clears_dummy_and_waits(self):
        update(self.root,NOW)
        update(self.root,NOW+timedelta(minutes=1),mode='real')
        self.assertEqual(read_json(self.root/'docs/data/latest.json'),[])
        self.assertEqual(read_json(self.root/'docs/data/status.json')['state'],'waiting_real')

    def test_real_mode_never_invents_or_retimes_measurements(self):
        row=normalize({'status':'OFFLINE','power_w':98,'time':'2026-10-17 08:55:00'},CONFIG['devices'][0],False)
        write_json(self.root/'data/real/latest.json',[row]);update(self.root,NOW,mode='real')
        published=read_json(self.root/'docs/data/latest.json')[0]
        self.assertIsNone(published['value']);self.assertFalse(published['is_demo']);self.assertEqual(published['measured_at'],'2026-10-17T08:55:00+09:00')
        update(self.root,NOW+timedelta(minutes=5))
        self.assertEqual(read_json(self.root/'docs/data/latest.json')[0]['measured_at'],published['measured_at'])

    def test_invalid_real_input_does_not_change_mode_or_public_data(self):
        update(self.root,NOW);before=(self.root/'docs/data/latest.json').read_bytes()
        row=normalize({'status':'NORMAL','power_w':10,'time':'2026-10-17 09:00:00'},CONFIG['devices'][0],False)
        for invalid in ({**row,'mac_addr':'synthetic-private-mac'},{**row,'is_demo':True},{**row,'sensor_id':'unregistered'},{**row,'source_url':'https://private.invalid'}):
            write_json(self.root/'data/real/latest.json',[invalid])
            with self.assertRaises(ValueError):update(self.root,NOW,mode='real')
            self.assertEqual(read_json(self.root/'config/monitor.json')['mode'],'dummy');self.assertEqual((self.root/'docs/data/latest.json').read_bytes(),before)

    def test_bad_settings_and_numbers_are_rejected(self):
        for changes in ({'mode':'unknown'},{'interval_minutes':0},{'interval_minutes':True},{'interval_minutes':1441},{'devices':[{'id':'bad:id','name':'bad'}]}):
            with self.assertRaises(ValueError):config_checked({**CONFIG,**changes})
        for changes in ({'power_state':'UNKNOWN_STATE'},{'value':float('nan')},{'ble_rssi':-128},{'node_rssi':float('inf')}):
            with self.assertRaises(ValueError):normalize({'power_state':'NORMAL','value':5,'measured_at':NOW.isoformat(),**changes},CONFIG['devices'][0])

    def test_pi_csv_uses_local_mapping_and_never_exports_private_identifiers(self):
        csv_path=self.root/'raw.csv';csv_path.write_text('time,id,room,mac_addr,status,power,ble_rssi,node_rssi\n2026-10-17 08:00:00,PRIVATE-HOSP,private-room,aa:bb:cc:dd:ee:ff,NORMAL,1,-50,-60\n2026-10-17 09:00:00,PRIVATE-HOSP,private-room,aa:bb:cc:dd:ee:ff,OFFLINE,20,-50,-60\n',encoding='utf-8')
        mapping={'aa:bb:cc:dd:ee:ff':'switchbot-001'};rows=convert(csv_path,mapping,CONFIG)
        self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['value']);self.assertFalse(rows[0]['is_demo'])
        encoded=json.dumps(rows);self.assertNotIn('aa:bb',encoded);self.assertNotIn('PRIVATE-HOSP',encoded);self.assertNotIn('private-room',encoded)
        map_path=self.root/'devices.local.json';write_json(map_path,mapping)
        with patch('raspi_bridge.subprocess.run',return_value=Mock(returncode=0)) as git:
            run(self.root,csv_path,map_path,True);run(self.root,csv_path,map_path,True)
            self.assertEqual(sum(call.args[0][-3:]==['push','origin','main'] for call in git.call_args_list),2,'Retry a pending push even when CSV values did not change')

    def test_pages_and_workflow_have_no_secret_or_arbitrary_polling(self):
        js=(ROOT/'docs/assets/app.js').read_text(encoding='utf-8')
        workflow=(ROOT/'.github/workflows/monitor.yml').read_text(encoding='utf-8')
        self.assertIn('credentials:\'omit\'',js);self.assertNotIn('Authorization',js);self.assertNotIn('localStorage',js)
        self.assertIn('3-58/5 * * * *',workflow);self.assertIn('workflow_dispatch:',workflow)
        self.assertLess(workflow.index('unittest discover'),workflow.index('scripts/monitor.py'))
        self.assertIn('actions/deploy-pages@v4',workflow)


if __name__=='__main__':unittest.main()
