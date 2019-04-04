# aclman

ACL manager for
the [Integrative Design, Arts and Technology (IDeATe)](https://ideate.cmu.edu/) Network
at [Carnegie Mellon University](https://www.cmu.edu/).

## Requirements

* Python 3

## Configuration

Copy the example configuration and place API endpoints, keys, etc., in `aclman/config/secrets.py`:

```
cp aclman/config/secrets{.example,}.py
edit aclman/config/secrets.py
```

## Usage

From the project root directory:

```
python3 -m aclman.aclman
```
