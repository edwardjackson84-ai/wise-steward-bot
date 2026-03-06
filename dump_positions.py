import requests, os, json
from tradelocker_executor import authenticate, TRADELOCKER_API_URL

def main():
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v

    token, acc_id, acc_num = authenticate()
    headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(acc_num),
        "Content-Type": "application/json"
    }

    pos_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/positions"
    print("Fetching positions...")
    resp = requests.get(pos_url, headers=headers)
    print(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    main()
