# qBittorrent Plugins

## Plugins

### Search

| Website | Plugin |
| ------- | ------ |
| [toloka.to](https://toloka.to) | [toloka_to.py](plugins/search/toloka_to.py) |

## Development Workflow

0. Prerequisite

   * A Linux-like environment
   * [Python](https://www.python.org/) installed
   * [uv](https://docs.astral.sh/uv/) installed

1. Setup development environment

   1. Setup virtual environment and dependencies

      ```shell
      uv sync
      ```

   2. Activate virtual environment

      ```shell
      source .venv/bin/activate
      ```

      or use `uv run <command>` to run a command inside virtual environment

2. Update stubs

   ```shell
   just stubs
   ```

3. Run type check

   ```shell
   just check
   ```

4. Run static analyzer

   ```shell
   just lint
   ```

5. Apply formatting

   ```shell
   just format
   ```

## References

* [How to write a search plugin](https://github.com/qbittorrent/search-plugins/wiki/How-to-write-a-search-plugin)
* [just - Command runner](https://just.systems/man/en/)
* [uv - Python package and project manager](https://docs.astral.sh/uv/)
