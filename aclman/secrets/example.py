# S3 API credentials
s3_api = {
  'hostname': 'https://s3svc.example.org',
  'username': 'S3_API_USERNAME',
  'password': 'S3_API_PASSWORD'
}
# CSGold Util server credentials
csgold_util = {
  'fqdn': 'csgold-util.example.org',
  'username': 'CSGOLD_UTIL_USERNAME',
  'ssh_key_path': '/path/to/csgold_util_ssh_key'
}
# Grouper credentials
grouper_api = {
  'hostname': 'https://grouper.example.org',
  'username': 'GROUPER_API_USERNAME',
  'password': 'GROUPER_API_PASSWORD'
}
# MRBS database credentials
mrbs_db = {
  'username': 'MRBS_DB_USERNAME',
  'password': 'MRBS_DB_PASSWORD'
}
# Stratasys Skylab API credentials
skylab_api = {
  'api_key': 'SKYLAB_API_KEY'
}
# Zoho API credentials
zoho_api = {
  'owner': 'ZOHO_OWNER_NAME',
  'application': 'ZOHO_APP_NAME',
  # Client ID and Client Secret come from https://api-console.zoho.com/
  # This server-based application is considered a "Self Client"
  'client_id': '1000.xxxxxxxxxxHF2C6H',
  'client_secret': 'xxxxxxxxx4f4f7a',
  # Refresh token is permanent (unless rotated), and comes from the setup
  # process described in the README under "Zoho API refresh token"
  # To generate, run the setup script: `python3 -m aclman.setup.zoho`
  'refresh_token': '1000.3ph66exxxxxxx6ce34.3c4xxxxxxxxxf'
}
