"""
Entrypoint for the aggregate portfolio dashboard server.
"""

import sys

# Ensure stdout/stderr use UTF-8 so Unicode characters from shared modules
# don't crash when the detached Windows process writes to redirected logs.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from aggregate_app import create_app
import aggregate_config

app = create_app()


if __name__ == "__main__":
    print("=" * 80)
    print("Programme Portfolio Aggregation Dashboard")
    print("=" * 80)
    print(f"Server URL: http://localhost:{aggregate_config.AGGREGATE_PORT}")
    print(f"Source DB (read-only): {aggregate_config.SOURCE_DATABASE_PATH}")
    print(f"Portfolio DB: {aggregate_config.PORTFOLIO_DATABASE_PATH}")
    print("=" * 80)
    print("\nAdmin APIs and dashboard shell are available on this server.")
    print("Press Ctrl+C to stop the aggregate server.\n")

    app.run(
        host=aggregate_config.AGGREGATE_HOST,
        port=aggregate_config.AGGREGATE_PORT,
        debug=aggregate_config.AGGREGATE_DEBUG,
    )
