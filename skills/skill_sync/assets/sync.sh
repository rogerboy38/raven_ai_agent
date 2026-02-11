#!/usr/bin/env bash
# Sync skill metadata to AGENTS.md Auto-invoke sections
# Adapted from Prowler for RavenAIAgent
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
APP_ROOT="$(dirname "$SKILLS_DIR")"
REPO_ROOT="$(dirname "$APP_ROOT")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DRY_RUN=false
FILTER_SCOPE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run) DRY_RUN=true; shift ;;
        --scope) FILTER_SCOPE="$2"; shift 2 ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--scope <scope>]"
            echo ""
            echo "Scopes: root, skills, api, providers"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Map scope to AGENTS.md path
# Matches Prowler pattern: each component can have its own AGENTS.md
get_agents_path() {
    case "$1" in
        root)      echo "$REPO_ROOT/AGENTS.md" ;;
        skills)    echo "$SKILLS_DIR/AGENTS.md" ;;
        api)       echo "$APP_ROOT/api/AGENTS.md" ;;
        providers) echo "$APP_ROOT/providers/AGENTS.md" ;;
        *)         echo "" ;;
    esac
}

# Extract YAML frontmatter field
extract_field() {
    local file="$1" field="$2"
    awk -v field="$field" '
        /^---$/ { in_fm = !in_fm; next }
        in_fm && $1 == field":" {
            sub(/^[^:]+:[[:space:]]*/, "")
            gsub(/^["'\'']|["'\'']$/, "")
            print
            exit
        }
    ' "$file"
}

# Extract nested metadata field (handles both single string and list)
# Returns: "action1;;action2;;action3" for lists (;; separator to avoid conflict with |)
extract_metadata() {
    local file="$1" field="$2"
    awk -v field="$field" '
        /^---$/ { in_fm = !in_fm; next }
        in_fm && /^metadata:/ { in_meta = 1; next }
        in_fm && in_meta && /^[a-z]/ && !/^[[:space:]]/ { in_meta = 0 }
        in_fm && in_meta && $1 == field":" {
            sub(/^[^:]+:[[:space:]]*/, "")
            # Single line value
            if ($0 != "" && $0 !~ /^\[/) { 
                gsub(/^["'\'']|["'\'']$/, "")
                print
                exit 
            }
            # Inline array [a, b, c]
            if ($0 ~ /^\[/) {
                gsub(/[\[\]]/, "")
                gsub(/,/, ";;")
                gsub(/[[:space:]]+/, "")
                print
                exit
            }
            # Multi-line list
            out = ""
            while (getline) {
                if ($0 ~ /^---$/) break
                if ($0 ~ /^[a-z]/ && $0 !~ /^[[:space:]]/) break
                if ($0 ~ /^[[:space:]]*-[[:space:]]*/) {
                    sub(/^[[:space:]]*-[[:space:]]*/, "")
                    gsub(/^["'\'']|["'\'']$/, "")
                    if ($0 != "") out = (out == "" ? $0 : out ";;" $0)
                } else break
            }
            if (out != "") print out
            exit
        }
    ' "$file"
}

echo -e "${BLUE}Skill Sync - Updating AGENTS.md Auto-invoke sections${NC}"
echo "========================================================"
echo ""

# Collect skills by scope: SCOPE_SKILLS[scope] = "skill1;;action1;;action2|skill2;;action3"
declare -A SCOPE_SKILLS

while IFS= read -r skill_file; do
    [ -f "$skill_file" ] || continue
    skill_name=$(extract_field "$skill_file" "name")
    scope_raw=$(extract_metadata "$skill_file" "scope")
    auto_invoke_raw=$(extract_metadata "$skill_file" "auto_invoke")
    
    [ -z "$skill_name" ] && continue
    [ -z "$scope_raw" ] || [ -z "$auto_invoke_raw" ] && continue
    
    # Parse scopes (remove brackets, split by ;;)
    scope_raw=$(echo "$scope_raw" | tr -d '[]')
    IFS=';;' read -ra scopes <<< "$scope_raw"
    
    for scope in "${scopes[@]}"; do
        scope=$(echo "$scope" | tr -d '[:space:],')
        [ -z "$scope" ] && continue
        [ -n "$FILTER_SCOPE" ] && [ "$scope" != "$FILTER_SCOPE" ] && continue
        
        # Store as: skill_name;;action1;;action2
        entry="$skill_name;;$auto_invoke_raw"
        
        if [ -z "${SCOPE_SKILLS[$scope]}" ]; then
            SCOPE_SKILLS[$scope]="$entry"
        else
            SCOPE_SKILLS[$scope]="${SCOPE_SKILLS[$scope]}|$entry"
        fi
    done
done < <(find "$SKILLS_DIR" -mindepth 2 -maxdepth 2 -name SKILL.md -print 2>/dev/null | sort)

# Generate Auto-invoke section for each scope
for scope in $(printf "%s\n" "${!SCOPE_SKILLS[@]}" | sort); do
    agents_path=$(get_agents_path "$scope")
    
    if [ -z "$agents_path" ]; then
        echo -e "${YELLOW}Warning: Unknown scope '$scope'${NC}"
        continue
    fi
    
    if [ ! -f "$agents_path" ]; then
        echo -e "${YELLOW}Warning: No AGENTS.md at $agents_path (skipping)${NC}"
        continue
    fi
    
    echo -e "${BLUE}Processing: $scope -> $agents_path${NC}"
    
    auto_invoke_section="### Auto-invoke Skills

When performing these actions, ALWAYS invoke the corresponding skill FIRST:

| Action | Skill |
|--------|-------|"

    # Parse entries and build rows
    IFS='|' read -ra skill_entries <<< "${SCOPE_SKILLS[$scope]}"
    for entry in "${skill_entries[@]}"; do
        # entry format: skill_name;;action1;;action2;;...
        IFS=';;' read -ra parts <<< "$entry"
        skill_name="${parts[0]}"
        
        # Skip first element (skill_name), iterate actions
        for ((i=1; i<${#parts[@]}; i++)); do
            action="${parts[$i]}"
            action=$(echo "$action" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
            [ -z "$action" ] && continue
            auto_invoke_section="$auto_invoke_section
| $action | \`$skill_name\` |"
        done
    done

    if $DRY_RUN; then
        echo -e "${YELLOW}[DRY RUN] Would update with:${NC}"
        echo "$auto_invoke_section"
        echo ""
    else
        section_file=$(mktemp)
        echo "$auto_invoke_section" > "$section_file"
        
        if grep -q "### Auto-invoke Skills" "$agents_path"; then
            awk '
                /^### Auto-invoke Skills/ {
                    while ((getline line < "'"$section_file"'") > 0) print line
                    close("'"$section_file"'")
                    skip = 1
                    next
                }
                skip && /^(---|## )/ { skip = 0; print "" }
                !skip { print }
            ' "$agents_path" > "$agents_path.tmp"
            mv "$agents_path.tmp" "$agents_path"
            echo -e "${GREEN}  ✓ Updated Auto-invoke section${NC}"
        else
            echo "" >> "$agents_path"
            cat "$section_file" >> "$agents_path"
            echo -e "${GREEN}  ✓ Inserted Auto-invoke section${NC}"
        fi
        rm -f "$section_file"
    fi
done

echo ""
echo -e "${GREEN}Done!${NC}"

# Show skills missing metadata
echo ""
echo -e "${BLUE}Skills missing sync metadata:${NC}"
missing=0
while IFS= read -r skill_file; do
    [ -f "$skill_file" ] || continue
    skill_name=$(extract_field "$skill_file" "name")
    scope_raw=$(extract_metadata "$skill_file" "scope")
    auto_invoke=$(extract_metadata "$skill_file" "auto_invoke")
    
    if [ -z "$scope_raw" ] || [ -z "$auto_invoke" ]; then
        echo -e "  ${YELLOW}$skill_name${NC} - missing: ${scope_raw:+}${scope_raw:-scope} ${auto_invoke:+}${auto_invoke:-auto_invoke}"
        missing=$((missing + 1))
    fi
done < <(find "$SKILLS_DIR" -mindepth 2 -maxdepth 2 -name SKILL.md -print 2>/dev/null | sort)

if [ $missing -eq 0 ]; then
    echo -e "  ${GREEN}All skills have sync metadata${NC}"
fi
