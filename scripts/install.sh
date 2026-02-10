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
            echo "  --tts=all          Install all TTS backends"
            echo "  -h, --help         Show this help message"
            exit 0
            ;;
    esac
done

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found. Please install Python 3.8 or higher.${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
    echo -e "${RED}Error: Python 3.8+ required, found $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python $PYTHON_VERSION found${NC}"
echo

# Check for pip
echo -e "${YELLOW}Checking for pip...${NC}"
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${RED}Error: pip not found. Please install pip first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ pip found${NC}"
echo

# Create virtual environment
echo -e "${YELLOW}Creating virtual environment...${NC}"
if [ -d ".venv" ]; then
    echo -e "${BLUE}Virtual environment already exists. Skipping creation.${NC}"
else
    python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi
echo

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
python -m pip install --upgrade pip --quiet
echo -e "${GREEN}✓ pip upgraded${NC}"
echo

# Install base requirements
echo -e "${YELLOW}Installing base requirements...${NC}"
echo -e "${BLUE}This may take a few minutes...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}✓ Base requirements installed${NC}"
echo

# Check for NVIDIA GPU
echo -e "${YELLOW}Checking for NVIDIA GPU...${NC}"
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    echo

    # Ask about CUDA libraries
    echo -e "${YELLOW}Do you want to install CUDA libraries for GPU acceleration? (y/N)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${YELLOW}Installing CUDA libraries...${NC}"
        pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
        echo -e "${GREEN}✓ CUDA libraries installed${NC}"
    else
        echo -e "${BLUE}Skipping CUDA libraries. You can install them later with:${NC}"
        echo -e "${BLUE}  pip install nvidia-cublas-cu12 nvidia-cudnn-cu12${NC}"
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
    pip install chatterbox-tts --no-deps 2>/dev/null && {
        echo -e "${GREEN}✓ Chatterbox TTS installed${NC}"
    } || {
        echo -e "${YELLOW}pip install failed. Trying source installation...${NC}"
        # Fallback: clone and install from source
        TEMP_DIR=$(mktemp -d)
        git clone --depth 1 https://github.com/resemble-ai/chatterbox "$TEMP_DIR/chatterbox" 2>/dev/null && {
            pip install --no-deps -e "$TEMP_DIR/chatterbox" 2>/dev/null && {
                echo -e "${GREEN}✓ Chatterbox TTS installed from source${NC}"
            } || {
                # Last resort: copy the module directly
                if [ -d "$TEMP_DIR/chatterbox/chatterbox" ]; then
                    cp -r "$TEMP_DIR/chatterbox/chatterbox" "$PROJECT_DIR/src/"
                    echo -e "${GREEN}✓ Chatterbox TTS module copied to src/${NC}"
                else
                    echo -e "${RED}✗ Failed to install Chatterbox TTS${NC}"
                    echo -e "${BLUE}  You can try manually: pip install chatterbox-tts --no-deps${NC}"
                fi
            }
        } || {
            echo -e "${RED}✗ Failed to clone Chatterbox repository${NC}"
        }
        rm -rf "$TEMP_DIR"
    }

    # Verify installation
    python -c "from chatterbox.tts import ChatterboxTTS; print('  ✓ Chatterbox import successful')" 2>/dev/null || {
        echo -e "${YELLOW}  Note: Chatterbox import test failed. It may still work at runtime.${NC}"
    }
    echo
}

install_qwen3() {
    echo -e "${YELLOW}Installing Qwen3-TTS...${NC}"
    pip install qwen-tts 2>/dev/null && {
        echo -e "${GREEN}✓ Qwen3-TTS installed${NC}"
    } || {
        echo -e "${YELLOW}pip install failed. Trying from source...${NC}"
        TEMP_DIR=$(mktemp -d)
        git clone --depth 1 https://github.com/QwenLM/Qwen3-TTS.git "$TEMP_DIR/qwen3-tts" 2>/dev/null && {
            pip install -e "$TEMP_DIR/qwen3-tts" 2>/dev/null && {
                echo -e "${GREEN}✓ Qwen3-TTS installed from source${NC}"
            } || {
                echo -e "${RED}✗ Failed to install Qwen3-TTS${NC}"
                echo -e "${BLUE}  You can try manually: pip install qwen-tts${NC}"
            }
        } || {
            echo -e "${RED}✗ Failed to clone Qwen3-TTS repository${NC}"
        }
        rm -rf "$TEMP_DIR"
    }

    # Optional: flash attention for faster inference
    echo -e "${YELLOW}Do you want to install flash-attn for faster Qwen3-TTS inference? (y/N)${NC}"
    echo -e "${BLUE}(Requires a compatible GPU and may take a while to compile)${NC}"
    read -r flash_response
    if [[ "$flash_response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${YELLOW}Installing flash-attn...${NC}"
        MAX_JOBS=4 pip install -U flash-attn --no-build-isolation 2>/dev/null && {
            echo -e "${GREEN}✓ flash-attn installed${NC}"
        } || {
            echo -e "${YELLOW}  flash-attn installation failed (optional - TTS will still work)${NC}"
        }
    fi

    # Verify installation
    python -c "from qwen_tts import Qwen3TTSModel; print('  ✓ Qwen3-TTS import successful')" 2>/dev/null || {
        echo -e "${YELLOW}  Note: Qwen3-TTS import test failed. It may still work at runtime.${NC}"
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
            all)
                install_chatterbox
                install_qwen3
                ;;
            *)
                echo -e "${RED}Unknown TTS backend: $TTS_BACKEND${NC}"
                echo -e "${BLUE}Available: chatterbox, qwen3, all${NC}"
                ;;
        esac
    else
        # Interactive TTS selection
        echo -e "${YELLOW}Which TTS backend(s) would you like to install?${NC}"
        echo "  1) Chatterbox TTS (ResembleAI - voice cloning, English)"
        echo "  2) Qwen3-TTS (Alibaba - multilingual, 10 languages, multiple voices)"
        echo "  3) Both"
        echo "  4) Skip TTS installation"
        echo
        read -r -p "Select (1-4): " tts_choice

        case $tts_choice in
            1)
                install_chatterbox
                ;;
            2)
                install_qwen3
                ;;
            3)
                install_chatterbox
                install_qwen3
                ;;
            4|*)
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
python -c "
from tts_provider import get_available_backends
backends = get_available_backends()
for name, avail in backends.items():
    status = '✓ installed' if avail else '✗ not installed'
    print(f'  {name}: {status}')
if not any(backends.values()):
    print('  No TTS backends available. Install with: ./scripts/install.sh --tts')
" 2>/dev/null || echo -e "${YELLOW}  Could not check TTS status (run from src/ directory)${NC}"
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
echo
echo -e "${YELLOW}Note: Remember to activate the virtual environment before running:${NC}"
echo -e "${GREEN}  source .venv/bin/activate${NC}"
echo
