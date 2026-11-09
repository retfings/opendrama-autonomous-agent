from __future__ import annotations
import argparse, logging, os
from pathlib import Path
from .dotenv_loader import load_env
from .config import load_config
from .controller import run, project_sessions
from .opencode import OpenCodeClient

def main():
    parser = argparse.ArgumentParser(description="OpenDrama autonomous R&D scheduler")
    parser.add_argument("command", choices=["check", "run"])
    parser.add_argument("--base", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    base = Path(args.base).resolve()
    load_env(base / ".env")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=base / "logs/scheduler.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = load_config(base)
    if args.command == "check":
        client = OpenCodeClient(cfg.opencode_url, cfg.username, cfg.password)
        print("Health:", client.health())
        for item in project_sessions(client, cfg):
            print(item)
        return
    print("Scheduler result:", run(base, cfg))

if __name__ == "__main__":
    main()
