# aclman

ACL manager for
the [Integrative Design, Arts and Technology (IDeATe)](https://ideate.cmu.edu/) Network
at [Carnegie Mellon University](https://www.cmu.edu/).

## Requirements

* Python >= 3.8
* `python3-venv` (for `pip` and `ensurepip`)
* A MySQL client.  Infrastructure servers running ACLMAN may already need,
  e.g., the `default-mysql-server` package.

## Setting up environments

This project uses `pyproject.toml` to establish dependencies for its build
environment.  The overall build process is described in general terms
[here](https://pip.pypa.io/en/stable/reference/build-system/pyproject-toml/).

### Build environment

Clone the repo and create a Python `venv` for the build environment:
```
git clone git@github.com:CMUIDeATe/aclman.git
cd ~/aclman
python3 -m venv .venv/ --prompt aclman-build
```

Install `pip` dependencies to the build environment:
```
source .venv/bin/activate
pip install --upgrade pip
pip install build
```

Install the package to the build environment in "editable" mode:
```
pip install -e .
```

To configure the build environment, copy the example configuration files to the
appropriate locations, and place API endpoints, keys, etc., in
`config/secrets.yaml` as appropriate:
```
cp config/config.development.yaml config/config.yaml
cp config/secrets.example.yaml config/secrets.yaml
edit config/secrets.yaml
```
The locations of these configuration files can also be overridden with
command-line options at invocation.

### Test and production environments

Create an `aclman` user which will run ACLMAN in production, and establish a
Python `venv` for each environment in which it will run:
```
sudo adduser --disabled-password aclman
sudo -s
python3 -m venv /opt/aclman-test/ --prompt aclman-test
python3 -m venv /opt/aclman-prod/ --prompt aclman-prod
chown -R aclman:aclman /opt/aclman-test/
chown -R aclman:aclman /opt/aclman-prod/
```

Then `su` as the new user and install `pip` dependencies to each environment
`$ENV`:
```
sudo su aclman
source /opt/$ENV/bin/activate
pip install --upgrade pip
pip install build
```

To configure the environment, copy the example configuration files from the
build environment to the appropriate locations, and place API endpoints, keys,
etc., in `/opt/$ENV/config/secrets.yaml` as appropriate:
```
mkdir /opt/$ENV/config

cp ~/aclman/config/config.development.yaml /opt/$ENV/config/config.yaml
[OR] cp ~/aclman/config/config.production.yaml /opt/$ENV/config/config.yaml

sudo cp ~/aclman/config/secrets.example.yaml /opt/$ENV/config/secrets.yaml
edit /opt/$ENV/config/secrets.yaml
```
The locations of these configuration files can also be overridden with
command-line options at invocation.

Ensure the proper permissions on these configuration files:
```
sudo -s
chmod 0644 /opt/$ENV/config/config.yaml
chmod 0640 /opt/$ENV/config/secrets.yaml
chown aclman:aclman /opt/$ENV/config/*.yaml
```

## Deploying to test and production

From the build directory and environment, build a wheel:
```
cd ~/aclman
source .venv/bin/activate
# Bump the project version and update any other dependencies
edit pyproject.toml
python3 -m build --wheel
```
This creates a wheel in the `dist` subdirectory.  If needed, copy it to the
target environment's host.

Using the target environment's `pip`, install the application from the latest
wheel created in the build environment's `dist` subdirectory, e.g.:
```
sudo /opt/$ENV/bin/pip install ~/aclman/dist/aclman-x.y.z-py3-none-any.whl
```
where `x.y.z` is the project version.

## Initialization

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

Make sure the SSH keys are copied into the location specified by `ssh_key_path`
for each environment.  The keys should be owned by the `aclman` user with
permissions set to `0600`.

### Zoho API refresh token
1. Log into https://api-console.zoho.com/
2. Select the "Self Client" which represents this server-based application.
   (If it doesn't exist, create one.)
3. Under "Client Secret", copy the Client ID and Client Secret, and place them
   in `config/secrets.yaml`
4. From the project root directory, run the setup script:
   `python3 -m aclman.setup.zoho`
    - Confirm the Client ID and Client Secret.
    - Follow the instructions in the setup script to request a (short-lived)
      authorization code for the app.
    - Proceed through the setup script to generate a (permanent) refresh token.
5. Place the generated refresh token in `config/secrets.yaml`.

## Usage

### Running from build

If not already active, activate the build environment:
```
cd ~/aclman
source .venv/bin/activate
```

Run `python3 -m aclman` with the desired options.

Add `-s FILE` or `--sectionfile FILE` to read the section file from `FILE`
instead of the default.  This is useful for testing with smaller datasets.  For
example:
```
python3 -m aclman -s src/data/test.csv
```

The locations used for logs (and configuration, unless overridden) are based on
the directory from which `aclman` is invoked.  See `python3 -m aclman --help`
for options.

### Running from test or production

Using the target environment's `python3`, enter the desired invocation
directory for logs and configuration, and run the application with the desired
options, e.g.:
```
sudo su aclman
cd /opt/$ENV
./bin/python3 -m aclman [options]
```

For production `cron`, this is generally best invoked under the `aclman` user as:
```
cd /opt/aclman-prod && ./bin/python3 -m aclman [options]
```
or, equivalently, if an unscheduled production run is required:
```
sudo su aclman -c "cd /opt/aclman-prod && ./bin/python3 -m aclman [options]"
```
