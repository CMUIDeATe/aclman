import sys
import datetime
import json
import urllib.request
import urllib.parse

from .. import config_handler
from .. import helpers
from ..api import zoho as Zoho

instrumented_opener = urllib.request.build_opener(helpers.CustomHTTPErrorHandler)
urllib.request.install_opener(instrumented_opener)

secrets = config_handler.get_secrets('zoho_api')

# Zoho Creator API v2 documentation
# https://www.zoho.com/creator/help/api/v2/
base_accounts_url = "https://accounts.zoho.com"
# Scopes documentation
# https://www.zoho.com/creator/help/api/v2/oauth-overview.html#scopes
scopes = "ZohoCreator.form.CREATE,ZohoCreator.report.READ,ZohoCreator.report.UPDATE"



print('''
Zoho API Refresh Token setup
''')

# https://www.zoho.com/creator/help/api/v2/authorization-request.html
print('''STEP 1.
  - Log into https://api-console.zoho.com/
  - Select the "Self Client" which represents this server-based application.
    (If it doesn't exist, create one.)
  - Under "Client Secret", confirm that the following Client ID and Client
    Secret match:
''')
print("          Client ID: %s" % secrets['client_id'])
print("      Client Secret: %s" % secrets['client_secret'])
print()
response = input("    Are these correct? (y/n) ")
if response.lower() not in ['y', 'yes']:
  print('''
Please put the proper Client ID and Client Secret in the secrets file and then
restart this script.
''')
  print("Aborted.")
  sys.exit(1)

# https://www.zoho.com/creator/help/api/v2/authorization-request.html#self_client
print()
print('''STEP 2.
  - Under "Generate Code", use the following scope and description:
     - Scope:
            %s
     - Description:
	    To allow ACLMAN middleware process to update and manage patron data
            and privileges.
  - Click "Create".
    This is known as the "authorization code" or sometimes "grant code" and
    must be exchanged for an access and refresh token within the specified
    (short!) timeframe.
  - To obtain a refresh token, ENTER THE AUTHORIZATION/GRANT CODE BELOW.
''' % scopes)
authorization_code = input("      Authorization code: ")
print()
# NOTE: Since this code is only valid for a few minutes, at most, we use it right away.

# Generate the refresh token.
# https://www.zoho.com/creator/help/api/v2/generate-token.html
print("    Requesting refresh token...")
endpoint = "%s/oauth/v2/token?client_id=%s&client_secret=%s&code=%s&grant_type=authorization_code" % (base_accounts_url, secrets['client_id'], secrets['client_secret'], authorization_code)
try:
  req = urllib.request.Request(endpoint, data=None, method='POST')
  resp = urllib.request.urlopen(req).read()
  resp_data = json.loads(resp.decode('utf-8'))
  if 'error' in resp_data:
    print('''
The Zoho API responded with the following error: '%s'
''' % resp_data['error'])
    print("Aborted.")
    sys.exit(2)
  access_token = resp_data['access_token']
  refresh_token = resp_data['refresh_token']
  expiration_time = datetime.datetime.now() + datetime.timedelta(seconds=resp_data['expires_in'])
  # NOTE: We don't actually bother using the access token (or its expiration
  # time) here; we're interested in the (permanent) refresh token which will
  # generate more.
except urllib.error.HTTPError as e:
  raise e

print('''STEP 3.
  - Place the following refresh token in the secrets file:
''')
print("      %s" % refresh_token)
print('''
    Note that refresh tokens don't expire.  If this token is compromised, it
    should be manually revoked and rotated.  For more details, see:
    https://help.zoho.com/portal/en/community/topic/does-the-refresh-token-expire
    https://www.zoho.com/creator/help/api/v2/revoke-tokens.html
''')
print("Done.")
sys.exit(0)
