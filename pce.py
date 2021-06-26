import os
import requests
from rest3client import RESTclient

class IllumioPCE:
    pce = ''
    pce_org = 1
    pce_api_user = ''
    pce_api_secret = ''

    def client_init(self):
        self.client = RESTclient(self.pce, username=self.pce_api_user, password=self.pce_api_secret)

# PCE API request call using requests module
    def request(self, verb, path, params=None, data=None, json=None, extra_headers=None):
        
        base_url = os.path.join(self.pce, 'api', 'v2', 'orgs', str(self.pce_org))
        headers = {
                  'user-agent': 'IllumioPCE class',
                }
        full_url = os.path.join(base_url, path)
        print(full_url)
        if extra_headers:
            headers.update(extra_headers)
            print(headers)
        if json:
            print(json)
        response = requests.request(verb, full_url,
                                    auth=(self.pce_api_user, self.pce_api_secret),
                                    headers=headers,
                                    params=params,
                                    json=json,
                                    data=data)
        return response
