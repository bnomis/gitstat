# Source this file: source bin/activate.sh
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$root/.venv/bin/activate"
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
unset root
