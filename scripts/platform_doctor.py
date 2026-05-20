#!/usr/bin/env python3
from remote_ops_workspace.doctor import run_doctor

if __name__ == "__main__":
    print(run_doctor().to_json())
