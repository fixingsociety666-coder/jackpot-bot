import requests

class QuestTradeAPI:
    def __init__(self, access_token, api_server):
        self.access_token = access_token
        self.api_server = api_server

    def get_positions(self):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        r = requests.get(f"{self.api_server}/v1/accounts", headers=headers)
        positions = []
        for acc in r.json().get("accounts", []):
            acc_id = acc["accountId"]
            r2 = requests.get(f"{self.api_server}/v1/accounts/{acc_id}/positions", headers=headers)
            positions.extend(r2.json().get("positions", []))
        return positions
