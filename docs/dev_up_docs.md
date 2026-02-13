# Devup File
Authors: Jeffery Eisenhardt, Cole Aydelotte, Collin Cabral-Castro.

# The What?

dev_up.sh is a one-command development bootstrap script that automatically prepares and launches the application’s local runtime environment.

When executed, the script:

- Creates an isolated Python virtual environment
- Activates the environment
- Installs all required dependencies from requirements.txt
- Installs the project as an editable package
- Configures PYTHONPATH so the src/ module can be resolved
- Starts the application using Gunicorn with the project’s configuration

In short, it provisions the environment and launches the backend in one process.

# The Why?

Setting up Python environments and starting services manually is repetitive and error-prone. Developers may forget steps, install packages globally, misconfigure paths, or start the server incorrectly.

This script exists to:
- Standardize environment setup across all machines
- Prevent dependency/version mismatches
- Eliminate manual configuration mistakes
- Speed up onboarding and daily startup
- Provide a single, reliable command to run the app

By automating setup and execution, development becomes consistent, reproducible, and fast, allowing contributors to focus on building features rather than configuring tooling.

# How to run

Make the script executable (first time only):
```bash
chmod +x dev_up.sh
```

Run the script:
```bash
./dev_up.sh
```

The server will start automatically after setup completes.
