import sys, datetime
sys.path.append('.')
from hankox_executor import is_session_active
print("US30:", is_session_active("US30"))
print("Current Time UTC:", datetime.datetime.utcnow())
