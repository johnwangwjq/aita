Aita is cli tool running test against an AI assistant API to see if it replies as expected.

# main project structure:

- `pyproject.toml` - project configure
- `README.md` - the document about what is aita, test yaml spec, how to run aita, etc.
- `aita/` - the source code
- `aita/__main__.py` - the entry point
- `aita/cli.py` - build commandline
- `aita/config.py` - load and parse the test configure
- `bin/aita` - the shell script for "aita" command to launch it
- `tests` - unittests. run test: `python -m unittest discover tests/`
- `.venv/` - the virtual environment

refer to the [readme](../../README.md) for the spec of test aita support.

# Rules on coding:
1. use as less as possible dependencies in python
2. follow the best practices of python
3. fail fast and early, ie., do not try-catch but let system throws, unless there is a business logic need
4. try to be functional(instead of object oriented) with minimal side effects
5. prefer (explicity + readability) over implicity and  performance
