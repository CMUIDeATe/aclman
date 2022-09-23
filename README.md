# aclman

ACL manager for
the [Integrative Design, Arts and Technology (IDeATe)](https://ideate.cmu.edu/) Network
at [Carnegie Mellon University](https://www.cmu.edu/).

## Requirements

* Python 3

## Installation

Create a user which will run ACLMAN in production, and establish a stable
location such as `/opt/aclman` where it will run:
```
sudo -s
adduser --disabled-password aclman
mkdir /opt/aclman
chown aclman:aclman /opt/aclman/
```

Then `su` as the new user, establish a read-only deploy key for this
repository, and clone this repository into the target location.

## Dependencies

* A MySQL client.  Infrastructure servers running ACLMAN may already need,
  e.g., the `default-mysql-server` package.

## Configuration

Copy the example configuration and place API endpoints, keys, etc., in
`aclman/secrets/{development,production}.py` as appropriate:
```
cp aclman/secrets/example.py aclman/secrets/development.py
cp aclman/secrets/example.py aclman/secrets/production.py
edit aclman/secrets/{development,production}.py
```

## Deployment and setup

### CSGold
To ensure that automatic SFTP connections to the CSGold Util server go through,
establish the server as a known host for the user running ACLMAN
by manually initiating an `sftp` connection to
the host listed in these secrets files as `csgold_util['fqdn']`.
It doesn't matter if these connections are accepted,
just that the hosts become known in `~/.ssh/known_hosts`:
```
sftp csgold-util.example.org
# Repeat for each environment
```

### Zoho API refresh token
1. Log into [https://api-console.zoho.com/]
2. Select the "Self Client" which represents this server-based application.
   (If it doesn't exist, create one.)
3. Under "Client Secret", copy the Client ID and Client Secret, and place them
   in `aclman/secrets/production.py`
4. From the project root directory, run the setup script:
   `python3 -m aclman.setup.zoho`
    - Confirm the Client ID and Client Secret.
    - Follow the instructions in the setup script to request a (short-lived)
      authorization code for the app.
    - Proceed through the setup script to generate a (permanent) refresh token.
5. Place the generated refresh token in `aclman/secrets/production.py`

## Updating

To pull the latest updates into production, just pull from the repository.
A typical user with `sudo` privileges will ordinarily accomplish this with:
```
sudo su aclman -c "cd /opt/aclman ; git pull origin main"
```
or, a bit more robustly:
```
sudo su aclman -c "cd /opt/aclman ; git fetch origin ; git reset --hard origin/main"
```

## Usage

From the project root directory, to conduct a dry-run in development
environments:
```
python3 -m aclman.aclman
```

Add `--live` to run in production.

For production `cron`, this is generally best invoked under the `aclman` user as:
```
cd /opt/aclman && python3 -m aclman.aclman --live
```
or, equivalently, if an unscheduled production run is required:
```
sudo su aclman -c "cd /opt/aclman && python3 -m aclman.aclman --live"
```
