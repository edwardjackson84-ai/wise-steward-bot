import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add parent dir to path so we can import hankox_executor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import hankox_executor

class TestConfigLoader(unittest.TestCase):

    @patch('hankox_executor.dotenv_values')
    @patch('hankox_executor.os.path.exists')
    @patch('hankox_executor.os.environ.get')
    def test_config_resolution_priority(self, mock_env_get, mock_exists, mock_dotenv):
        # We simulate checking for .env.atlasdemo
        
        # Scenario 1: File exists in WISE_STEWARD_CONFIG_DIR, script_dir, and /etc/secrets
        # Priority should be WISE_STEWARD_CONFIG_DIR
        mock_env_get.side_effect = lambda k: "/mock/custom/dir" if k == "WISE_STEWARD_CONFIG_DIR" else None
        
        def mock_exists_side_effect(path):
            if "toggles.json" in path: return False
            if ".env.atlasdemo" in path:
                return True
            return False
            
        mock_exists.side_effect = mock_exists_side_effect
        mock_dotenv.return_value = {"ACCOUNT_ACTIVE": "True"}
        
        hankox_executor.env_files = [".env.atlasdemo"]
        
        configs = hankox_executor.get_active_configs()
        
        # Verify it was called with the highest priority dir
        mock_dotenv.assert_called_with(os.path.join("/mock/custom/dir", ".env.atlasdemo"))
        self.assertEqual(len(configs), 1)

    @patch('hankox_executor.dotenv_values')
    @patch('hankox_executor.os.path.exists')
    @patch('hankox_executor.os.environ.get')
    def test_config_resolution_fallback(self, mock_env_get, mock_exists, mock_dotenv):
        # Scenario 2: File exists ONLY in /etc/secrets
        mock_env_get.side_effect = lambda k: "/mock/custom/dir" if k == "WISE_STEWARD_CONFIG_DIR" else None
        
        def mock_exists_side_effect(path):
            if "toggles.json" in path: return False
            if path == os.path.join("/etc/secrets", ".env.atlasdemo"):
                return True
            return False
            
        mock_exists.side_effect = mock_exists_side_effect
        mock_dotenv.return_value = {"ACCOUNT_ACTIVE": "True"}
        
        hankox_executor.env_files = [".env.atlasdemo"]
        
        configs = hankox_executor.get_active_configs()
        
        # Verify it fell back to /etc/secrets
        mock_dotenv.assert_called_with(os.path.join("/etc/secrets", ".env.atlasdemo"))
        self.assertEqual(len(configs), 1)

    @patch('hankox_executor.get_active_configs')
    @patch('hankox_executor.notify_telegram')
    def test_startup_health_check_zero_accounts(self, mock_notify, mock_get_configs):
        # Scenario 3: Verify check_startup_health exits with 3 if zero accounts are found
        # Telegram creds exist, but zero active accounts.
        mock_get_configs.return_value = [] # No files found
        
        with patch.dict('os.environ', {"TELEGRAM_BOT_TOKEN": "test", "TELEGRAM_CHAT_ID": "test"}):
            with self.assertRaises(SystemExit) as cm:
                hankox_executor.check_startup_health()
                
            self.assertEqual(cm.exception.code, 3)
            mock_notify.assert_called_once()

if __name__ == '__main__':
    unittest.main()
