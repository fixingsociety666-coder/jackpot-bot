import requests
from config import QUESTRADE_CLIENT_ID, QUESTRADE_REFRESH_TOKEN

class QuestTradeOAuth:
    def __init__(self):
        self.client_id = QUESTRADE_CLIENT_ID
        self.refresh_token = QUESTRADE_REFRESH_TOKEN
        self.api_server = None
        self.access_token = None

    def refresh_access_token(self):
        url = "https://login.questrade.com/oauth2/token"
        params = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token
        }
        r = requests.get(url, params=params).json()
        self.access_token = r.get("access_token")
        self.api_server = r.get("api_server")
        return self.access_token, self.api_server
