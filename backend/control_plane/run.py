"""Run one controller process with explicitly loaded private configuration."""

import argparse
from pathlib import Path

from pydantic import ValidationError

from control_plane.environment import load_settings_file


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = load_settings_file(args.env_file)
    except (OSError, ValueError, ValidationError) as error:
        print("Cannot load private server configuration:", type(error).__name__)
        return 2
    import uvicorn

    from control_plane.main import create_app

    uvicorn.run(
        create_app(config),
        host=config.HOST,
        port=config.PORT,
        workers=1,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1,::1",
        ws_max_size=6 * 1024 * 1024,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
