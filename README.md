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

## Usage

From the project root directory, to conduct a dry-run in development
environments:

```
python3 -m aclman.aclman
```

Add `--live` to run in production.
