#!/bin/bash
set -e  # Exit on error

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Whispering Installation Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Parse arguments
INSTALL_TTS=false
TTS_BACKEND=""
for arg in "$@"; do
    case $arg in
        --tts)
            INSTALL_TTS=true
            ;;
        --tts=*)
            INSTALL_TTS=true
            TTS_BACKEND="${arg#*=}"
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --tts              Install TTS backends (interactive selection)"
            echo "  --tts=chatterbox   Install Chatterbox TTS backend"
            echo "  --tts=qwen3        Install Qwen3-TTS backend"
            echo "  --tts=kokoro       Install Kokoro TTS backend (lightweight 82M model)"
            echo "  --tts=all          Install all TTS backends"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
    esac
done

# Detect a usable Python command (python3, python, or whatever the venv exposes)
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}Error: python3/python not found. Please install Python 3.8 or higher.${NC}"
    exit 1
fi

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${RED}Error: Python 3.8+ required, found $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION found (${PYTHON_CMD})${NC}"
echo

# Create virtual environment (skip if one is already active)
if [ -n "$VIRTUAL_ENV" ]; then
    echo -e "${BLUE}Virtual environment already active: $VIRTUAL_ENV${NC}"
elif [ -n "$CONDA_PREFIX" ]; then
    echo -e "${BLUE}Conda environment already active: $CONDA_PREFIX${NC}"
else
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    if [ -d ".venv" ]; then
        echo -e "${BLUE}Virtual environment already exists. Activating it.${NC}"
    else
        $PYTHON_CMD -m venv .venv
        echo -e "${GREEN}✓ Virtual environment created${NC}"
    fi
    echo

    # Activate virtual environment
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
fi
echo

# After venv is active, prefer 'python' (the venv binary)
for cmd in python python3; do
    if command -v "$cmd" &> /dev/null; then
        PYTHON_CMD="$cmd"
        break
    fi
done

# Check for pip (now inside the venv)
echo -e "${YELLOW}Checking for pip...${NC}"
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo -e "${YELLOW}pip not found in environment. Installing pip...${NC}"
    $PYTHON_CMD -m ensurepip --default-pip 2>/dev/null || {
        echo -e "${RED}Error: Could not install pip. Please install pip manually:${NC}"
        echo -e "${RED}  $PYTHON_CMD -m ensurepip --default-pip${NC}"
        echo -e "${RED}  or: curl -sS https://bootstrap.pypa.io/get-pip.py | $PYTHON_CMD${NC}"
        exit 1
    }
fi
echo -e "${GREEN}✓ pip found${NC}"
echo

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
$PYTHON_CMD -m pip install --upgrade pip --quiet
echo -e "${GREEN}✓ pip upgraded${NC}"
echo

# Install base requirements
echo -e "${YELLOW}Installing base requirements...${NC}"
echo -e "${BLUE}This may take a few minutes...${NC}"
$PYTHON_CMD -m pip install -r requirements.txt
echo -e "${GREEN}✓ Base requirements installed${NC}"
echo

# Check for NVIDIA GPU and auto-install CUDA libraries if needed
echo -e "${YELLOW}Checking for NVIDIA GPU...${NC}"
HAS_GPU=false
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    HAS_GPU=true
    echo

    # Auto-install CUDA libraries that match PyTorch's build.
    # CRITICAL: version mismatch causes CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH.
    # We detect the exact cuDNN version PyTorch was compiled with and install that.
    echo -e "${YELLOW}Checking CUDA library compatibility...${NC}"
    CUDNN_OK=false
    CUDNN_MATCH=$($PYTHON_CMD -c "
import torch, importlib, json, re, sys
# Get the cuDNN version PyTorch was built with
built = torch.backends.cudnn.version()  # e.g. 90100 for 9.1.0
if not built:
    sys.exit(1)
major, minor, patch = built // 10000, (built % 10000) // 100, built % 100
# Check currently installed nvidia-cudnn version
try:
    dist = importlib.metadata.distribution('nvidia-cudnn-cu12')
    installed = dist.version  # e.g. '9.1.0.70'
    inst_parts = installed.split('.')
    if int(inst_parts[0]) == major and int(inst_parts[1]) == minor:
        print('MATCH')
    else:
        print(f'{major}.{minor}.{patch}')
except importlib.metadata.PackageNotFoundError:
    print(f'{major}.{minor}.{patch}')
" 2>/dev/null)

    if [ "$CUDNN_MATCH" = "MATCH" ]; then
        echo -e "${GREEN}✓ CUDA libraries already installed and version-matched${NC}"
        CUDNN_OK=true
    elif [ -n "$CUDNN_MATCH" ]; then
        # Need to install the matching cuDNN version
        CUDNN_MAJOR_MINOR=$(echo "$CUDNN_MATCH" | cut -d. -f1,2)
        echo -e "${YELLOW}Installing cuDNN ${CUDNN_MAJOR_MINOR}.x to match PyTorch build...${NC}"
        # Pin to the major.minor that PyTorch expects
        $PYTHON_CMD -m pip install "nvidia-cudnn-cu12>=${CUDNN_MAJOR_MINOR}.0,<${CUDNN_MAJOR_MINOR%.*}.$((${CUDNN_MAJOR_MINOR#*.}+1)).0" nvidia-cublas-cu12 --quiet 2>/dev/null && {
            echo -e "${GREEN}✓ CUDA libraries installed (cuDNN ${CUDNN_MAJOR_MINOR}.x)${NC}"
            CUDNN_OK=true
        } || {
            echo -e "${YELLOW}⚠ Pinned cuDNN install failed. Trying generic...${NC}"
            $PYTHON_CMD -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 --quiet 2>/dev/null
        }
    else
        # No torch or no CUDA build — install generic
        echo -e "${YELLOW}Installing CUDA libraries...${NC}"
        $PYTHON_CMD -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 --quiet 2>/dev/null && {
            echo -e "${GREEN}✓ CUDA libraries installed${NC}"
        } || {
            echo -e "${YELLOW}⚠ CUDA libraries installation failed (non-critical)${NC}"
            echo -e "${BLUE}  GPU acceleration may still work via system CUDA.${NC}"
        }
    fi

    # Verify cuDNN actually works with PyTorch
    if [ "$CUDNN_OK" = true ]; then
        $PYTHON_CMD -c "
import torch
assert torch.backends.cudnn.is_available(), 'cuDNN not available'
v = torch.backends.cudnn.version()
print(f'  cuDNN version: {v // 10000}.{(v % 10000) // 100}.{v % 100}')
# Quick smoke test: run a small conv on GPU to trigger cuDNN init
if torch.cuda.is_available():
    x = torch.randn(1, 1, 8, 8, device='cuda')
    torch.nn.functional.conv2d(x, torch.randn(1, 1, 3, 3, device='cuda'))
    print('  cuDNN smoke test: passed')
" 2>/dev/null || {
            echo -e "${YELLOW}⚠ cuDNN smoke test failed. TTS will auto-fallback to non-cuDNN mode.${NC}"
        }
    fi
else
    echo -e "${BLUE}No NVIDIA GPU detected. CPU mode will be used.${NC}"
fi
echo

# Create necessary directories
echo -e "${YELLOW}Creating project directories...${NC}"
mkdir -p log_output
mkdir -p tts_output
mkdir -p tts_voices
echo -e "${GREEN}✓ Directories created${NC}"
echo

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f "config/.env.example" ]; then
        echo -e "${YELLOW}Creating .env file from template...${NC}"
        cp config/.env.example .env
        echo -e "${GREEN}✓ .env file created${NC}"
        echo -e "${BLUE}Note: Edit .env file to add your API keys${NC}"
    else
        echo -e "${BLUE}No .env.example found. Skipping .env creation.${NC}"
    fi
else
    echo -e "${BLUE}.env file already exists. Skipping.${NC}"
fi
echo

# Make scripts executable
echo -e "${YELLOW}Making scripts executable...${NC}"
chmod +x scripts/run.sh
chmod +x scripts/debug_env.sh 2>/dev/null || true
echo -e "${GREEN}✓ Scripts are executable${NC}"
echo

# ========================================
# TTS Installation
# ========================================

install_chatterbox() {
    echo -e "${YELLOW}Installing Chatterbox TTS...${NC}"
    echo -e "${BLUE}Note: Chatterbox requires specific dependency handling.${NC}"

    # Check Python version for distutils compatibility
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
        echo -e "${YELLOW}Python $PYTHON_VERSION detected. Using --no-deps to avoid distutils issues.${NC}"
    fi

    # Install chatterbox without dependencies (deps already in requirements.txt)
    $PYTHON_CMD -m pip install chatterbox-tts --no-deps 2>/dev/null && {
        echo -e "${GREEN}✓ Chatterbox TTS installed${NC}"
    } || {
        echo -e "${YELLOW}pip install failed. Trying source installation...${NC}"
        # Fallback: clone and install from source
        TEMP_DIR=$(mktemp -d)
        git clone --depth 1 https://github.com/resemble-ai/chatterbox "$TEMP_DIR/chatterbox" 2>/dev/null && {
            $PYTHON_CMD -m pip install --no-deps -e "$TEMP_DIR/chatterbox" 2>/dev/null && {
                echo -e "${GREEN}✓ Chatterbox TTS installed from source${NC}"
            } || {
                # Last resort: copy the module directly
                if [ -d "$TEMP_DIR/chatterbox/chatterbox" ]; then
                    cp -r "$TEMP_DIR/chatterbox/chatterbox" "$PROJECT_DIR/src/"
                    echo -e "${GREEN}✓ Chatterbox TTS module copied to src/${NC}"
                else
                    echo -e "${RED}✗ Failed to install Chatterbox TTS${NC}"
                    echo -e "${BLUE}  You can try manually: $PYTHON_CMD -m pip install chatterbox-tts --no-deps${NC}"
                fi
            }
        } || {
            echo -e "${RED}✗ Failed to clone Chatterbox repository${NC}"
        }
        rm -rf "$TEMP_DIR"
    }

    # Verify installation
    $PYTHON_CMD -c "from chatterbox.tts import ChatterboxTTS; print('  ✓ Chatterbox import successful')" 2>/dev/null || {
        echo -e "${YELLOW}  Note: Chatterbox import test failed. It may still work at runtime.${NC}"
    }
    echo
}

install_flash_attn() {
    # Install flash-attn (REQUIRED for Qwen3-TTS).
    # Strategy: try pre-built wheel first (fast, no compiler needed),
    #           then fall back to building from source.

    echo -e "${YELLOW}Installing flash-attn (required for Qwen3-TTS)...${NC}"

    # Check if already installed
    if $PYTHON_CMD -c "import flash_attn; print(f'flash-attn {flash_attn.__version__} already installed')" 2>/dev/null; then
        echo -e "${GREEN}✓ flash-attn already installed${NC}"
        return 0
    fi

    # Detect Python version, torch version, and CUDA version for pre-built wheel
    PY_VER=$($PYTHON_CMD -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')" 2>/dev/null)
    TORCH_VER=$($PYTHON_CMD -c "import torch; v=torch.__version__.split('+')[0].rsplit('.',1)[0]; print(v)" 2>/dev/null)
    CUDA_VER=$($PYTHON_CMD -c "
import torch
cv = torch.version.cuda
if cv:
    parts = cv.split('.')
    print(f'cu{parts[0]}{parts[1]}')
else:
    print('')
" 2>/dev/null)

    echo -e "${BLUE}  Detected: Python=${PY_VER}, PyTorch=${TORCH_VER}, CUDA=${CUDA_VER}${NC}"

    FLASH_ATTN_INSTALLED=false

    # --- Attempt 1: Pre-built wheel from mjun0812 (fastest, no compiler needed) ---
    if [ -n "$CUDA_VER" ] && [ -n "$TORCH_VER" ] && [ -n "$PY_VER" ]; then
        echo -e "${YELLOW}  Trying pre-built wheel (no compilation needed)...${NC}"

        # Try flash-attn versions from newest to oldest
        for FA_VER in 2.8.3 2.7.4 2.6.3; do
            WHEEL_NAME="flash_attn-${FA_VER}+${CUDA_VER}torch${TORCH_VER}-${PY_VER}-${PY_VER}-linux_x86_64.whl"
            # Try multiple release tags (the repo uses incrementing tags)
            for RELEASE_TAG in v0.7.16 v0.7.15 v0.7.13 v0.7.12 v0.7.11; do
                WHEEL_URL="https://github.com/mjun0812/flash-attention-prebuild-wheels/releases/download/${RELEASE_TAG}/${WHEEL_NAME}"
                echo -e "${BLUE}    Trying: flash-attn ${FA_VER} from ${RELEASE_TAG}...${NC}"
                if $PYTHON_CMD -m pip install "$WHEEL_URL" 2>/dev/null; then
                    echo -e "${GREEN}✓ flash-attn ${FA_VER} installed from pre-built wheel${NC}"
                    FLASH_ATTN_INSTALLED=true
                    break 2
                fi
            done
        done
    fi

    # --- Attempt 2: Build from source with --no-build-isolation ---
    if [ "$FLASH_ATTN_INSTALLED" = false ]; then
        echo -e "${YELLOW}  Pre-built wheel not found. Building from source...${NC}"
        echo -e "${BLUE}  This may take several minutes to compile...${NC}"
        MAX_JOBS=4 $PYTHON_CMD -m pip install -U flash-attn --no-build-isolation 2>&1 | tail -5
        if $PYTHON_CMD -c "import flash_attn" 2>/dev/null; then
            echo -e "${GREEN}✓ flash-attn installed (built from source)${NC}"
            FLASH_ATTN_INSTALLED=true
        fi
    fi

    # --- Attempt 3: Try the official Dao-AILab release wheels ---
    if [ "$FLASH_ATTN_INSTALLED" = false ] && [ -n "$CUDA_VER" ] && [ -n "$TORCH_VER" ] && [ -n "$PY_VER" ]; then
        echo -e "${YELLOW}  Trying official GitHub release wheels...${NC}"
        # The official repo uses slightly different naming
        for FA_VER in 2.7.4 2.6.3; do
            WHEEL_NAME="flash_attn-${FA_VER}+${CUDA_VER}torch${TORCH_VER}cxx11abiFALSE-${PY_VER}-${PY_VER}-linux_x86_64.whl"
            WHEEL_URL="https://github.com/Dao-AILab/flash-attention/releases/download/v${FA_VER}/${WHEEL_NAME}"
            echo -e "${BLUE}    Trying: official flash-attn ${FA_VER}...${NC}"
            if $PYTHON_CMD -m pip install "$WHEEL_URL" 2>/dev/null; then
                echo -e "${GREEN}✓ flash-attn ${FA_VER} installed from official wheel${NC}"
                FLASH_ATTN_INSTALLED=true
                break
            fi
            # Try with cxx11abiTRUE
            WHEEL_NAME="flash_attn-${FA_VER}+${CUDA_VER}torch${TORCH_VER}cxx11abiTRUE-${PY_VER}-${PY_VER}-linux_x86_64.whl"
            WHEEL_URL="https://github.com/Dao-AILab/flash-attention/releases/download/v${FA_VER}/${WHEEL_NAME}"
            if $PYTHON_CMD -m pip install "$WHEEL_URL" 2>/dev/null; then
                echo -e "${GREEN}✓ flash-attn ${FA_VER} installed from official wheel${NC}"
                FLASH_ATTN_INSTALLED=true
                break
            fi
        done
    fi

    if [ "$FLASH_ATTN_INSTALLED" = false ]; then
        echo -e "${RED}✗ flash-attn installation failed${NC}"
        echo -e "${RED}  flash-attn is REQUIRED for Qwen3-TTS.${NC}"
        echo -e "${BLUE}  Manual install options:${NC}"
        echo -e "${BLUE}    1. Pre-built wheel: visit https://flashattn.dev and download for your config${NC}"
        echo -e "${BLUE}    2. Build from source: MAX_JOBS=4 pip install flash-attn --no-build-isolation${NC}"
        echo -e "${BLUE}    3. Check https://github.com/mjun0812/flash-attention-prebuild-wheels/releases${NC}"
        return 1
    fi

    return 0
}

install_qwen3() {
    echo -e "${YELLOW}Installing Qwen3-TTS...${NC}"
    $PYTHON_CMD -m pip install qwen-tts 2>/dev/null && {
        echo -e "${GREEN}✓ Qwen3-TTS installed${NC}"
    } || {
        echo -e "${YELLOW}pip install failed. Trying from source...${NC}"
        TEMP_DIR=$(mktemp -d)
        git clone --depth 1 https://github.com/QwenLM/Qwen3-TTS.git "$TEMP_DIR/qwen3-tts" 2>/dev/null && {
            $PYTHON_CMD -m pip install -e "$TEMP_DIR/qwen3-tts" 2>/dev/null && {
                echo -e "${GREEN}✓ Qwen3-TTS installed from source${NC}"
            } || {
                echo -e "${RED}✗ Failed to install Qwen3-TTS${NC}"
                echo -e "${BLUE}  You can try manually: $PYTHON_CMD -m pip install qwen-tts${NC}"
            }
        } || {
            echo -e "${RED}✗ Failed to clone Qwen3-TTS repository${NC}"
        }
        rm -rf "$TEMP_DIR"
    }

    # Install flash-attn (REQUIRED)
    install_flash_attn

    # Verify installation - suppress the qwen_tts flash-attn warning during check
    $PYTHON_CMD -W ignore -c "
import warnings, io, sys
# Suppress all output from qwen_tts import (it prints a flash-attn warning)
_stderr = sys.stderr
sys.stderr = io.StringIO()
try:
    from qwen_tts import Qwen3TTSModel
    import flash_attn
    sys.stderr = _stderr
    print('  ✓ Qwen3-TTS + flash-attn verified')
except ImportError as e:
    sys.stderr = _stderr
    print(f'  ✗ Import failed: {e}')
" 2>/dev/null || {
        echo -e "${RED}  ✗ Qwen3-TTS verification failed${NC}"
    }
    echo
}

install_kokoro() {
    echo -e "${YELLOW}Installing Kokoro TTS...${NC}"

    # Check for espeak-ng system dependency.
    # On Arch/Manjaro the legacy 'espeak' (1.48) package conflicts with
    # espeak-ng (1.50+).  phonemizer's "tie" option needs >=1.49, so we
    # must ensure espeak-ng wins.
    if ! command -v espeak-ng &> /dev/null; then
        echo -e "${YELLOW}espeak-ng not found. Attempting to install...${NC}"
        if command -v apt-get &> /dev/null; then
            sudo apt-get install -y espeak-ng 2>/dev/null && {
                echo -e "${GREEN}✓ espeak-ng installed${NC}"
            } || {
                echo -e "${YELLOW}⚠ Could not install espeak-ng automatically.${NC}"
                echo -e "${BLUE}  Please install manually: sudo apt-get install espeak-ng${NC}"
            }
        elif command -v pacman &> /dev/null; then
            # espeak-ng conflicts with legacy espeak; let pacman resolve it
            sudo pacman -S --noconfirm espeak-ng 2>/dev/null || {
                echo -e "${YELLOW}⚠ pacman could not install espeak-ng (legacy espeak conflict?)${NC}"
                echo -e "${BLUE}  Try: sudo pacman -Rdd espeak && sudo pacman -S espeak-ng${NC}"
            }
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y espeak-ng 2>/dev/null || true
        else
            echo -e "${YELLOW}⚠ Please install espeak-ng manually for your distribution.${NC}"
        fi
    else
        echo -e "${GREEN}✓ espeak-ng already installed${NC}"
    fi

    # kokoro → misaki[en] → spacy-curated-transformers → spacy>=4.0.0dev
    # spacy 4 doesn't exist as a stable release yet, so pip tries to build
    # 4.0.0.dev3 from source which fails.
    #
    # Strategy:
    #   1) Try normal pip install with a constraint pinning spacy<4.
    #   2) If that fails (spacy-curated-transformers needs spacy 4), fall back
    #      to --no-deps for kokoro and install its runtime deps manually,
    #      skipping spacy-curated-transformers (espeak-ng handles English G2P).

    KOKORO_INSTALLED=false

    # --- Attempt 1: Normal install with spacy<4 constraint ---
    echo -e "${YELLOW}  Attempting normal install (constraining spacy<4)...${NC}"
    CONSTRAINTS=$(mktemp)
    echo "spacy<4.0.0" > "$CONSTRAINTS"
    $PYTHON_CMD -m pip install kokoro soundfile -c "$CONSTRAINTS" 2>/dev/null && {
        KOKORO_INSTALLED=true
        echo -e "${GREEN}✓ Kokoro TTS installed${NC}"
    }
    rm -f "$CONSTRAINTS"

    # --- Attempt 2: Manual dep install, skip conflicting spacy-curated-transformers ---
    if [ "$KOKORO_INSTALLED" = false ]; then
        echo -e "${YELLOW}  Normal install failed. Installing with manual dependency management...${NC}"
        # Install kokoro itself without resolving transitive deps
        $PYTHON_CMD -m pip install kokoro --no-deps --quiet 2>/dev/null
        # Install its direct runtime deps (torch/numpy/scipy/transformers already present)
        $PYTHON_CMD -m pip install loguru soundfile --quiet 2>/dev/null
        # Install misaki without the [en] extra first (base G2P)
        $PYTHON_CMD -m pip install "misaki>=0.7.4" --quiet 2>/dev/null
        # Install English G2P extras that don't conflict
        $PYTHON_CMD -m pip install num2words phonemizer --quiet 2>/dev/null
        # Verify it actually loads
        if $PYTHON_CMD -c "from kokoro import KPipeline" 2>/dev/null; then
            KOKORO_INSTALLED=true
            echo -e "${GREEN}✓ Kokoro TTS installed (without spacy-curated-transformers)${NC}"
            echo -e "${BLUE}  Note: English G2P uses espeak-ng as the phonemizer backend.${NC}"
        fi
    fi

    if [ "$KOKORO_INSTALLED" = false ]; then
        echo -e "${RED}✗ Failed to install Kokoro TTS${NC}"
        echo -e "${BLUE}  You can try manually:${NC}"
        echo -e "${BLUE}    $PYTHON_CMD -m pip install kokoro --no-deps${NC}"
        echo -e "${BLUE}    $PYTHON_CMD -m pip install loguru soundfile 'misaki>=0.7.4' num2words phonemizer${NC}"
    fi

    # Final verification
    $PYTHON_CMD -c "from kokoro import KPipeline; print('  ✓ Kokoro import verified')" 2>/dev/null || {
        echo -e "${YELLOW}  ⚠ Kokoro import test failed.${NC}"
    }
    echo
}

# Handle TTS installation
if [ "$INSTALL_TTS" = true ]; then
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}TTS Backend Installation${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo

    if [ -n "$TTS_BACKEND" ]; then
        case $TTS_BACKEND in
            chatterbox)
                install_chatterbox
                ;;
            qwen3)
                install_qwen3
                ;;
            kokoro)
                install_kokoro
                ;;
            all)
                install_chatterbox
                install_qwen3
                install_kokoro
                ;;
            *)
                echo -e "${RED}Unknown TTS backend: $TTS_BACKEND${NC}"
                echo -e "${BLUE}Available: chatterbox, qwen3, kokoro, all${NC}"
                ;;
        esac
    else
        # Interactive TTS selection
        echo -e "${YELLOW}Which TTS backend(s) would you like to install?${NC}"
        echo "  1) Chatterbox TTS (ResembleAI - voice cloning, English)"
        echo "  2) Qwen3-TTS (Alibaba - multilingual, 10 languages, multiple voices)"
        echo "  3) Kokoro TTS (lightweight 82M model, fast, 54 voices, 9 languages)"
        echo "  4) All"
        echo "  5) Skip TTS installation"
        echo
        read -r -p "Select (1-5): " tts_choice

        case $tts_choice in
            1)
                install_chatterbox
                ;;
            2)
                install_qwen3
                ;;
            3)
                install_kokoro
                ;;
            4)
                install_chatterbox
                install_qwen3
                install_kokoro
                ;;
            5|*)
                echo -e "${BLUE}Skipping TTS installation.${NC}"
                echo -e "${BLUE}You can install later with: ./scripts/install.sh --tts${NC}"
                ;;
        esac
    fi
else
    echo -e "${BLUE}TTS backends not installed by default.${NC}"
    echo -e "${BLUE}To install TTS, run: ./scripts/install.sh --tts${NC}"
    echo
fi

# Verify TTS status
echo -e "${YELLOW}Checking TTS backend status...${NC}"
cd "$PROJECT_DIR/src" && $PYTHON_CMD -c "
from tts_provider import get_available_backends
backends = get_available_backends()
for name, avail in backends.items():
    status = '✓ installed' if avail else '✗ not installed'
    print(f'  {name}: {status}')
if not any(backends.values()):
    print('  No TTS backends available. Install with: ./scripts/install.sh --tts')
" 2>/dev/null && cd "$PROJECT_DIR" || { cd "$PROJECT_DIR"; echo -e "${YELLOW}  Could not check TTS status${NC}"; }
echo

# Installation complete
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. Run the GUI:     ${GREEN}./scripts/run.sh${NC}"
echo -e "  2. Run the TUI:     ${GREEN}python src/tui.py${NC}"
echo -e "  3. See README.md for usage instructions"
echo
echo -e "${BLUE}Optional setup:${NC}"
echo -e "  - For AI features: Edit .env and set OPENROUTER_API_KEY"
echo -e "  - For TTS: ${GREEN}./scripts/install.sh --tts${NC}"
echo -e "    Or install individually:"
echo -e "    - Chatterbox: ${GREEN}pip install chatterbox-tts --no-deps${NC}"
echo -e "    - Qwen3-TTS: ${GREEN}pip install qwen-tts${NC}"
echo -e "    - Kokoro:     ${GREEN}pip install kokoro soundfile${NC} (+ apt install espeak-ng)"
echo
echo -e "${YELLOW}Note: Remember to activate the virtual environment before running:${NC}"
echo -e "${GREEN}  source .venv/bin/activate${NC}"
echo
