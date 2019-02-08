# A stupid hack to be used as a tox install_command instead of the default.

# This installs one package as editable.  The typical use case is for
# relforge_* to depend on the local version of relforge
#
# tox.ini usage:
#   install_command = {toxinidir}/../relforge {opts} {packages}

set -e
pip install "--editable=$1"
shift
pip install "$@"
