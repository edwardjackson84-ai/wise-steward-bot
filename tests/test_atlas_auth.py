import sys
sys.path.append('.')
from hankox_executor import get_active_configs, authenticate_tradelocker
configs = get_active_configs()
atlas_cfg = next((c for c in configs if "atlas" in c["name"].lower()), None)
if atlas_cfg:
    print(f"Config accNum: {atlas_cfg['acc_num']}")
    token, acc_id, acc_num = authenticate_tradelocker(atlas_cfg)
    print(f"Auth returned: acc_id={acc_id}, acc_num={acc_num}")
