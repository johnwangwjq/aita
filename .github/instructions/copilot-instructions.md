 
 # Rules on coding:
 1. use as less as possible dependencies in python
 2. follow the best practices of python
 3. fail fast and early, ie., do not try-catch but let system throws, unless there is a business logic need
 4. try to be functional(instead of object oriented) with minimal side effects
 5. prefer (explicity + readability) over implicity and  performance


 Use the virtual environment `.venv` in the project root to manage dependencies and isolate the project environment.

 run test: `python -m unittest discover tests/`