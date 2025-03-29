# License Plate Detector

## Overview
A robust license plate detection system that processes video files to extract license plates using configurable parameters.

## Installation
- Ensure you have Python 3.x installed.
- Install dependencies:
  ```
  pip install -r requirements.txt
  ```
- Setup environment variables as needed.

## Usage
- Run the application:
  ```
  python3 main.py
  ```
- Alternatively, use the provided Makefile target:
  ```
  make lpdetector
  ```

## Configuration
- Customize settings in `config.py` such as video folder, output folder, and detection parameters.
- Logging is set up via `utils/logging_setup.py`.

## License
[MIT](LICENSE)
