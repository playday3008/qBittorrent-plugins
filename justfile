PY_FILES := `find plugins -type f -name '*.py' -printf '%p '`

# Show available recipes to run
default:
    just --list

# Byte-compile files
build files=PY_FILES:
    python \
        -m compileall \
        {{ files }}

# Run type check
check files=PY_FILES:
    mypy \
        {{ files }}
    pyright \
        {{ files }}

# Apply formatting
format files=PY_FILES:
    pycodestyle \
        --ignore=E265,E402,W503 \
        --max-line-length=1000 \
        --statistics \
        {{ files }}
    isort \
        --line-length 1000 \
        {{ files }}
    just \
        --fmt \
        --unstable

# Run static analyzer
lint files=PY_FILES:
    pyflakes \
        {{ files }}
    bandit \
        --skip B110,B310,B314,B405 \
        {{ files }}

# Run tests
test files='tests/*.py':
    pytest \
        --showlocals \
        {{ files }}

# Generate type stubs from qBittorrent search engine source (Unix)
[unix]
stubs:
    #!/usr/bin/env bash
    set -euo pipefail
    NOVA3_DIR="src/searchengine/nova3"
    TEMP_DIR=$(mktemp -d)
    QBT_DIR="$TEMP_DIR/qbt"
    trap "rm -rf $TEMP_DIR" EXIT

    # Clone only the nova3 directory
    git clone --filter=blob:none --sparse \
        https://github.com/qbittorrent/qBittorrent.git "$QBT_DIR"
    cd "$QBT_DIR"
    git sparse-checkout set "$NOVA3_DIR"

    # Find all Python files (excluding __init__ and socks)
    mapfile -t FILES < <(find "$NOVA3_DIR" -maxdepth 1 -name "*.py" \
        ! -name "__init__.py" \
        ! -name "socks.py" \
        -printf "%f\n")

    # Generate stubs for filtered files
    cd -
    for file in "${FILES[@]}"; do
        stubgen --output "$TEMP_DIR/stubs" "$QBT_DIR/$NOVA3_DIR/$file"
    done

    # Move stubs to project root and add commit hash header
    mkdir -p stubs
    for file in "${FILES[@]}"; do
        stub_file="${file%.py}.pyi"
        [[ -f "$TEMP_DIR/stubs/nova3/$stub_file" ]] || continue

        # Get commit hash for this specific file
        commit_hash=$(cd "$QBT_DIR" && git log -1 --format=%H -- "$NOVA3_DIR/$file")
        commit_date=$(cd "$QBT_DIR" && git log -1 --format=%ci -- "$NOVA3_DIR/$file")

        # Prepend header with commit info
        {
            echo "# Generated from: https://github.com/qbittorrent/qBittorrent/blob/$commit_hash/$NOVA3_DIR/$file"
            echo "# Commit: $commit_hash"
            echo "# Date: $commit_date"
            echo ""
            cat "$TEMP_DIR/stubs/nova3/$stub_file"
        } > "stubs/$stub_file"
    done

    echo "Stubs generated in stubs/"

# Generate type stubs from qBittorrent search engine source (Windows)
[windows]
stubs:
    #!pwsh
    $ErrorActionPreference = "Stop"
    $NOVA3_DIR = "src/searchengine/nova3"
    $TEMP_DIR = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    $QBT_DIR = Join-Path $TEMP_DIR "qbt"

    try {
        # Clone only the nova3 directory
        git clone --filter=blob:none --sparse `
            https://github.com/qbittorrent/qBittorrent.git $QBT_DIR
        Push-Location $QBT_DIR
        git sparse-checkout set $NOVA3_DIR

        # Find all Python files (excluding __init__ and socks)
        $FILES = Get-ChildItem -Path $NOVA3_DIR -Filter "*.py" |
            Where-Object { $_.Name -notin @("__init__.py", "socks.py") } |
            Select-Object -ExpandProperty Name

        # Generate stubs for filtered files
        Pop-Location
        foreach ($file in $FILES) {
            stubgen --output "$TEMP_DIR/stubs" "$QBT_DIR/$NOVA3_DIR/$file"
        }

        # Move stubs to project root and add commit hash header
        New-Item -ItemType Directory -Force -Path "stubs" | Out-Null
        foreach ($file in $FILES) {
            $stub_file = $file -replace '\.py$', '.pyi'
            $stub_path = "$TEMP_DIR/stubs/nova3/$stub_file"
            if (-not (Test-Path $stub_path)) { continue }

            # Get commit hash for this specific file
            Push-Location $QBT_DIR
            $commit_hash = git log -1 --format=%H -- "$NOVA3_DIR/$file"
            $commit_date = git log -1 --format=%ci -- "$NOVA3_DIR/$file"
            Pop-Location

            # Prepend header with commit info
            $header = @(
                "# Generated from: https://github.com/qbittorrent/qBittorrent/blob/$commit_hash/$NOVA3_DIR/$file"
                "# Commit: $commit_hash"
                "# Date: $commit_date"
                ""
            )
            $content = Get-Content $stub_path -Raw
            ($header -join "`n") + $content | Set-Content "stubs/$stub_file" -NoNewline
        }

        Write-Host "Stubs generated in stubs/"
    }
    finally {
        if (Test-Path $TEMP_DIR) {
            Remove-Item -Recurse -Force $TEMP_DIR
        }
    }
