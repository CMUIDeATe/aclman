# aclman

ACL manager for
the [Integrative Design, Arts and Technology (IDeATe)](https://ideate.cmu.edu/) Network
at [Carnegie Mellon University](https://www.cmu.edu/).

## Requirements

* Python 3

## Configuration

Copy the example configuration and place API endpoints, keys, etc., in
`aclman/secrets/{development,production}.py` as appropriate:

```
cp aclman/secrets/example.py aclman/secrets/development.py
cp aclman/secrets/example.py aclman/secrets/production.py
edit aclman/secrets/{development,production}.py
```

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

## Usage

From the project root directory, to conduct a dry-run in development
environments:

```
python3 -m aclman.aclman
```

Add `--live` to run in production.

For production `cron`, this is generally best invoked as:

```
cd /opt/aclman && python3 -m aclman.aclman --live
```
