import json
import os
import subprocess

# os.setuid(110)  # landscape user

completed_process = subprocess.run(
    ["pro", "status", "--format", "json"],
    encoding="utf8",
    stdout=subprocess.PIPE,
)

dat = json.loads(completed_process.stdout)
print(json.dumps(dat, indent=2))
print(os.geteuid())
