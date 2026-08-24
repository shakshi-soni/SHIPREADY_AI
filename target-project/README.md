# Project

## Setup
To set up the project locally, follow these steps:
1. Clone the repository to your local machine.
2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - On macOS/Linux:
     ```bash
     source venv/bin/activate
     ```
   - On Windows:
     ```bash
     venv/Scripts/activate
     ```
4. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage
To run the application, execute the main entry point:
```bash
python main.py
```
To run the test suite and verify that everything is working correctly, use pytest:
```bash
pytest
```

## Architecture
The project is structured as a standard Python application designed for reliability and maintainability:
- **Entrypoint**: The application is initialized and run from the main entrypoint file, which configures the environment and starts the service.
- **Dependencies**: External libraries and frameworks are managed via requirements.txt to ensure consistent environments across deployments.
- **Testing**: A comprehensive test suite is located in the tests/ directory, allowing for automated verification of business logic and endpoints using pytest.