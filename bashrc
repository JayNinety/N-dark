#
# ~/.bashrc
#

# If not running interactively, don't do anything
[[ $- != *i* ]] && return

# cd: change directory and print the resulting full path.
cd() {
    builtin cd "$@" || return $?
    printf '→ '
    pwd
}

# Command-specific output colors using your Micro theme palette.
# Colors are 24-bit RGB values, so they closely match Micro's theme.

alias ls='ls --color=auto'
alias grep='grep --color=auto'

# cat: file contents in constant.string (#98C379).
cat() {
    printf '\033[38;2;152;195;121m'
    command cat "$@"
    local status=$?
    printf '\033[0m'
    return "$status"
}

# pwd: current full path in identifier blue (#61AFEF).
pwd() {
    printf '\033[38;2;97;175;239m'
    builtin pwd "$@"
    local status=$?
    printf '\033[0m'
    return "$status"
}

# mv: verbose move results in statement purple (#C678DD).
mv() {
    printf '\033[38;2;198;120;221m'
    command mv -v "$@"
    local status=$?
    printf '\033[0m'
    return "$status"
}

# cp: verbose copy results in type cyan (#66D9EF).
cp() {
    printf '\033[38;2;102;217;239m'
    command cp -v "$@"
    local status=$?
    printf '\033[0m'
    return "$status"
}

# Current directory in the same blue used by pwd (#61AFEF).
# Prompt symbols retain your terminal's default foreground color.
PS1='\[\e[38;2;97;175;239m\]$( [[ "$PWD" != "$HOME" ]] && printf "[%s]" "${PWD##*/}" )\[\e[0m\]❯❯❯❯❯❯❯'

echo "╦ ╦┌─┐┬  ┌─┐┌─┐┌┬┐┌─┐
║║║├┤ │  │  │ ││││├┤ 
╚╩╝└─┘┴─┘└─┘└─┘┴ ┴└─┘"
echo "tools: cds, ch, zt, td, githelp, emount"

# Audio Share helper
as-start() {
    # Kill any previous instance first
    pkill -f "as-cmd" 2>/dev/null

    # Give PipeWire a moment if needed
    sleep 1

    # Start in background, log everything
    nohup as-cmd \
        --bind=192.168.0.230 \
        --encoding=f32 \
        --channels=2 \
        --sample-rate=48000 \
        --endpoint 31 \
        > /tmp/as-cmd.log 2>&1 &

    echo "as-cmd started (PID $!)"
    echo "Log: /tmp/as-cmd.log"
}

as-stop() {
    pkill -f "as-cmd" && echo "as-cmd stopped" || echo "as-cmd was not running"
}

as-status() {
    if pgrep -f "as-cmd" > /dev/null; then
        echo "as-cmd is running"
        ss -tulnp | grep 65530
    else
        echo "as-cmd is NOT running"
    fi
}

# Change Directory Selection
cds() {
  local include_hidden=false
  local target="."

  # Optional leading "." for hidden entries
  if [[ "$1" == "." ]]; then
    include_hidden=true
    shift
  fi

  # Optional path (supports spaces when quoted)
  if [[ $# -gt 0 ]]; then
    target="$1"
  fi

  # Sanity check
  if [[ ! -d "$target" ]]; then
    echo "Not a directory: $target"
    return 1
  fi

  local search_dir="${target%/}"
  [[ -z "$search_dir" ]] && search_dir="."

  local dirs=()
  local d name

  if $include_hidden; then
    for d in "$search_dir"/.[!.]* "$search_dir"/..?* "$search_dir"/*/ ; do
      [[ -d "$d" ]] || continue
      name="${d#"$search_dir"/}"
      name="${name%/}"
      [[ "$name" == "." || "$name" == ".." ]] && continue
      dirs+=("$name")
    done
  else
    for d in "$search_dir"/*/ ; do
      [[ -d "$d" ]] || continue
      name="${d#"$search_dir"/}"
      name="${name%/}"
      dirs+=("$name")
    done
  fi

  # Robust sort (handles spaces in names)
  IFS=$'\n' dirs=($(printf '%s\n' "${dirs[@]}" | sort -f))
  unset IFS

  (( ${#dirs[@]} == 0 )) && { echo "No directories found."; return 1; }

  local selected=0
  local offset=0
  local key
  local header_lines=2
  local height=$(( $(tput lines) - header_lines - 2 ))
  (( height < 5 )) && height=10
  (( height > ${#dirs[@]} )) && height=${#dirs[@]}

  local menu_lines=$(( height + header_lines ))

  tput civis

  _cds_draw() {
    local i end=$(( offset + height ))
    (( end > ${#dirs[@]} )) && end=${#dirs[@]}

    printf "Select directory (↑/↓, Enter to cd, q to cancel)\n\n"
    for (( i=offset; i<end; i++ )); do
      if (( i == selected )); then
        printf "  \e[7m %s \e[0m\n" "${dirs[i]}"
      else
        printf "    %s\n" "${dirs[i]}"
      fi
    done
  }

  _cds_draw

  while true; do
    IFS= read -rsn1 key
    if [[ $key == $'\x1b' ]]; then
      read -rsn2 key
      case $key in
        '[A') # Up
          (( selected > 0 )) && ((selected--))
          (( selected < offset )) && ((offset--))
          ;;
        '[B') # Down
          (( selected < ${#dirs[@]}-1 )) && ((selected++))
          (( selected >= offset + height )) && ((offset++))
          ;;
        '[5') # Page Up
          (( selected -= height ))
          (( selected < 0 )) && selected=0
          (( offset = selected ))
          ;;
        '[6') # Page Down
          (( selected += height ))
          (( selected >= ${#dirs[@]} )) && selected=$((${#dirs[@]}-1))
          (( offset = selected - height + 1 ))
          (( offset < 0 )) && offset=0
          ;;
      esac
    elif [[ $key == "" ]]; then
      break
    elif [[ $key == "q" || $key == "Q" ]]; then
      tput cuu $menu_lines
      tput ed
      tput cnorm
      return 0
    fi

    tput cuu $menu_lines
    tput ed
    _cds_draw
  done

  tput cuu $menu_lines
  tput ed
  tput cnorm

  builtin cd -- "$search_dir/${dirs[selected]}" || return 1
  printf "→ $(pwd)"
}

#ch command helper:
ch() {
  local include_hidden=false
  local pre_cmd=""

  # Parse arguments: optional leading "." for hidden, then optional command
  if [[ "$1" == "." ]]; then
    include_hidden=true
    shift
  fi
  if [[ $# -gt 0 ]]; then
    pre_cmd="$*"
  fi

  local items=()
  local d

  if $include_hidden; then
    for d in .[!.]* ..?* * .* *; do
      [[ -e "$d" ]] || continue
      [[ "$d" == "." || "$d" == ".." ]] && continue
      if [[ -d "$d" ]]; then
        items+=("${d%/}/")
      else
        items+=("$d")
      fi
    done
  else
    for d in *; do
      [[ -e "$d" ]] || continue
      if [[ -d "$d" ]]; then
        items+=("${d%/}/")
      else
        items+=("$d")
      fi
    done
  fi

  IFS=$'\n' items=($(printf '%s\n' "${items[@]}" | sort -fu))
  unset IFS

  (( ${#items[@]} == 0 )) && { echo "No files or directories found."; return 1; }

  local selected=0
  local offset=0
  local key
  local header_lines=2
  local height=$(( $(tput lines) - header_lines - 2 ))
  (( height < 5 )) && height=10
  (( height > ${#items[@]} )) && height=${#items[@]}

  local menu_lines=$(( height + header_lines ))

  tput civis

  _ch_draw() {
    local i end=$(( offset + height ))
    (( end > ${#items[@]} )) && end=${#items[@]}

    printf "Select file/folder (↑/↓, Enter to choose, q to cancel)\n\n"
    for (( i=offset; i<end; i++ )); do
      if (( i == selected )); then
        printf "  \e[7m %s \e[0m\n" "${items[i]}"
      else
        printf "    %s\n" "${items[i]}"
      fi
    done
  }

  _ch_draw

  while true; do
    IFS= read -rsn1 key
    if [[ $key == $'\x1b' ]]; then
      read -rsn2 key
      case $key in
        '[A') # Up
          (( selected > 0 )) && ((selected--))
          (( selected < offset )) && ((offset--))
          ;;
        '[B') # Down
          (( selected < ${#items[@]}-1 )) && ((selected++))
          (( selected >= offset + height )) && ((offset++))
          ;;
        '[5') # Page Up
          (( selected -= height ))
          (( selected < 0 )) && selected=0
          (( offset = selected ))
          ;;
        '[6') # Page Down
          (( selected += height ))
          (( selected >= ${#items[@]} )) && selected=$((${#items[@]}-1))
          (( offset = selected - height + 1 ))
          (( offset < 0 )) && offset=0
          ;;
      esac
    elif [[ $key == "" ]]; then
      break
    elif [[ $key == "q" || $key == "Q" ]]; then
      tput cuu $menu_lines
      tput ed
      tput cnorm
      return 0
    fi

    tput cuu $menu_lines
    tput ed
    _ch_draw
  done

  # Clear the menu
  tput cuu $menu_lines
  tput ed
  tput cnorm

  local chosen="${items[selected]}"
  local is_dir=false
  [[ "$chosen" == */ ]] && is_dir=true
  chosen="${chosen%/}"

  # Use pre-typed command or ask for one
  local cmd
  if [[ -n "$pre_cmd" ]]; then
    cmd="$pre_cmd"
  else
    read -e -p "type the command: " cmd
    [[ -z "$cmd" ]] && return 0
  fi

  # Special handling for directories
  if $is_dir; then
    case "$cmd" in
      cp)  cmd="cp -r" ;;
      rm)  cmd="rm -rf" ;;
    esac
  fi

  # Build the final command with proper quoting
  # Special case: "./" → ./"binary"  (no space)
  local final_cmd
  if [[ "$cmd" == "./" ]]; then
    final_cmd="./\"$chosen\""
  else
    final_cmd="$cmd \"$chosen\""
  fi

  # Put it on the command line so you only need to press Enter
  read -e -i "$final_cmd" -p "$ " to_run
  [[ -n "$to_run" ]] && eval "$to_run"
}
