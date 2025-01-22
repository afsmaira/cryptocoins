import sys
import requests
import json
import os
from dotenv import load_dotenv
load_dotenv()

from tqdm import tqdm

from binance import Client, ThreadedWebsocketManager, ThreadedDepthCacheManager
from binance.exceptions import BinanceAPIException

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os.path
import pickle

class Crypto():
    def __init__(self):
        self.stables = ['USDT', 'TUSD', 'USDC', 'USDP']
        api_key = os.getenv('BINANCE_API_KEY')          # Binance API key
        secret = os.getenv('BINANCE_SECRET')            # Binance Secret key
        self.client = Client(api_key, secret)
        self.id = int(os.getenv('BINANCE_ID'))          # Binance user ID
        self.p_lim = 2

    def isOn(self):
        return self.account()['uid'] == self.id

    def account(self):
        return self.client.get_account()
    
    def codes(self):
        return list(map(lambda x: x['asset'], self.account()['balances']))

    def avFrom(self):
        return list(map(lambda x: x['asset'], filter(lambda x: float(x['free']) > 0, self.account()['balances'])))

    def depth(self, to_code, from_code='USDT'):
        return self.client.get_order_book(symbol=to_code+from_code)

    def pressure(self, to_code, from_code='USDT'):
        if from_code == to_code: return 1
        try:
            d = self.depth(to_code)
        except BinanceAPIException:
            if from_code == 'USDT': return 0
            return self.pressure(to_code)/self.pressure(from_code)
        mb = sum(float(a)*float(b) for a,b in d['bids'])
        if mb == 0: return 0
        ma = sum(float(a)*float(b) for a,b in d['asks'])
        if ma == 0: return float('inf')
        return mb/ma

    def best(self, num=None, lim=None):
        if lim is None: lim = self.p_lim
        best = []
        for code in (pbar := tqdm(self.codes())):
            pbar.set_description(code)
            if code in self.stables: continue
            best.append((self.pressure(code), code))
        best = sorted(best, reverse=True)
        best = [[b[1], b[0], False] for b in best]
        if num is not None:
            best = best[:num]
        if lim is not None:
            best = list(filter(lambda x: x[1] > lim, best))
        return best

    def test(self):
        pass

class Sheet():
    # https://developers.google.com/identity/protocols/oauth2/web-server#offline
    def __init__(self):
        self.id = os.getenv('GOOGLE_SHEET_ID')
        self.cnf = os.getenv('GOOGLE_CREDS_FILE')
        self.T = 60
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets']
        self.service = None
        self.login()
        self.ss = self.service.spreadsheets()
        self.col_symb, self.col_p, self.col_buy = self.getCols()

    def login(self):
        creds = None
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.cnf, self.scopes)
                creds = flow.run_local_server(port=0)
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('sheets', 'v4', credentials=creds)

    def read(self, rng):
        result = self.ss.values().get(spreadsheetId=self.id, range=rng).execute()
        return result.get('values', [])

    def write(self, values, rng):
        # Escreve dados na planilha
        body = { 'values': values }
        result = self.ss.values().update(spreadsheetId=self.id, range=rng, valueInputOption='RAW', body=body).execute()
        return result.get("updatedCells")

    def getCols(self):    
        headers = self.read('Cripto!1:1')[0]
        return chr(ord('A') + headers.index('Símbolo')), \
               chr(ord('A') + headers.index('Pressão')), \
               chr(ord('A') + headers.index('Comprado'))

    def col2i(self, col):
        return ord(col) - ord(col_type)

    def val(self, v, i):
        return v[i] if i < len(v) else ''

    def getData(self):
        d = self.read(f'Cripto!{self.col_symb}2%3A{self.col_buy}')
        print(d)
        return [(r + 2, val(d, self.col2i(self.col_symb)),
                        val(d, self.col2i(self.col_p)),
                        val(d, self.col2i(self.col_buy))
                )
                for r, d in enumerate(data)
                ]

    def update(self, data, token=None):
        return self.write(data, f"Cripto!{self.col_symb}2:{self.col_buy}{len(data)+1}")

if __name__ == '__main__':
    c = Crypto()
    if len(sys.argv) == 1:
        s = Sheet()
        s.update(c.best())
    elif len(sys.argv) == 2:
        code = sys.argv[1]
        print(code, c.pressure(code))
    
