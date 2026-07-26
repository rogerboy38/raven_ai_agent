#!/bin/sh
# F-S12-2 guard, ported from amb_w_tds (SYM-001) — fail LOUD, never strip silently.
# Usable as pre-commit hook (.git/hooks/pre-commit -> ../../scripts/check_repo_hygiene.sh) and in CI.
# Origin here: 3 absolute-path symlinks (tmp, raven_ai_agent/tmp, public/node_modules)
# swept in by blanket `git add` automation, caught by Node A's leg-1 bake gate 2026-07-26.
set -u
fail=0

# 1. No committed symlinks, period. Any symlink either self-aliases the tree or
#    encodes one substrate's absolute paths — both poison a pinned bake.
links=$(git ls-files -s | awk '$1 == 120000 {print $4}')
if [ -n "$links" ]; then
    echo "HYGIENE FAIL: committed symlink(s) — remove at source, do NOT strip in bakes:"
    echo "$links" | sed 's/^/  /'
    fail=1
fi

# 2. No committed bytecode (the same blanket-add vector).
pyc=$(git ls-files | grep -E '\.pyc$|__pycache__' || true)
if [ -n "$pyc" ]; then
    echo "HYGIENE FAIL: committed bytecode:"
    echo "$pyc" | sed 's/^/  /'
    fail=1
fi

[ $fail -eq 0 ] && echo "repo hygiene OK (0 symlinks, 0 bytecode)"
exit $fail
