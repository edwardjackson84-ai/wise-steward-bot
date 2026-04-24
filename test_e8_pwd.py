import requests

def debug_e8_passwords():
    api_url = "https://demo.tradelocker.com/backend-api"
    email = "edward.jackson84@gmail.com"
    server = "E8"
    
    passwords_to_try = [
        "Qrl#Y0@t",
        "Qr1#Y0@t",
        "Qrl#YO@t",
        "Qr1#YO@t"
    ]
    
    for pwd in passwords_to_try:
        print(f"Trying password: {pwd}")
        resp = requests.post(
            f"{api_url}/auth/jwt/token",
            json={"email": email, "password": pwd, "server": server},
            headers={"accept": "application/json", "Content-Type": "application/json"}
        )
        if resp.status_code == 201:
            print(f"SUCCESS with password: {pwd}")
            return
        else:
            print(f"Failed: {resp.text}\n")

if __name__ == "__main__":
    debug_e8_passwords()
