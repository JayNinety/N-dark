#!/usr/bin/env bash

open_file() {
    local name="${1##*/}"
    echo "Opening File [${name}]..."
    zathura -- "$1" >/dev/null 2>&1 &
}

set -uo pipefail

# ---------- Extension lists ----------
DOC_EXTS=(
    pdf djvu djv ps eps
    epub cbz cbr
    odt ods odp
    doc docx xls xlsx ppt pptx
    rtf txt md markdown rst
    tex dvi xps oxps
    fb2 mobi azw azw3 chm
)

IMG_EXTS=(
    png jpg jpeg jpe jfif
    gif bmp dib tif tiff
    webp avif heic heif
    jxl jp2 j2k jpf jpx
    psd psb ico cur
    svg svgz apng
    ppm pgm pbm pnm pfm pam
    tga dds exr hdr pcx
    xcf raw dng cr2 cr3 nef nrw
    arw srf sr2 orf rw2 pef raf
    wmf emf fits fit
)

CONVERT_EXTS=(
    webp avif heic heif jxl
    jp2 j2k jpf jpx
    psd psb
    svg svgz
    wmf emf
)

if ! command -v zathura >/dev/null 2>&1; then
    printf 'Error: zathura is not installed.\n' >&2
    exit 1
fi

IM_CMD=""
if command -v magick >/dev/null 2>&1; then
    IM_CMD="magick"
elif command -v convert >/dev/null 2>&1; then
    IM_CMD="convert"
fi

declare -A DOC_SET=()
declare -A IMG_SET=()
declare -A CONVERT_SET=()
declare -A ALLOWED_SET=()

for ext in "${DOC_EXTS[@]}"; do
    DOC_SET["$ext"]=1
    ALLOWED_SET["$ext"]=1
done
for ext in "${IMG_EXTS[@]}"; do
    IMG_SET["$ext"]=1
    ALLOWED_SET["$ext"]=1
done
for ext in "${CONVERT_EXTS[@]}"; do
    CONVERT_SET["$ext"]=1
done

# ---------- Helper: open a single file (with conversion if needed) ----------
open_selected() {
    local SELECTED="$1"
    local NAME="${SELECTED##*/}"
    local EXT="${NAME##*.}"
    EXT="${EXT,,}"

    # No extension or unknown extension → force conversion attempt
    local force_convert=false
    if [[ "$NAME" != *.* ]] || [[ -z "${ALLOWED_SET[$EXT]+yes}" ]]; then
        force_convert=true
        EXT="unknown"
    fi

    # Known document → open directly
    if [[ -n "${DOC_SET[$EXT]+yes}" ]]; then
        open_file "$SELECTED"
        return
    fi

    # Known image that doesn't need conversion
    if ! $force_convert && [[ -z "${CONVERT_SET[$EXT]+yes}" ]]; then
        open_file "$SELECTED"
        return
    fi

    # Needs conversion (CONVERT_EXTS or unknown/no extension)
    if [[ -z "$IM_CMD" ]]; then
        printf 'ImageMagick is required to convert %s.\n' "$EXT" >&2
        printf 'Install ImageMagick; trying original...\n' >&2
        open_file "$SELECTED"
        return
    fi

    local SELECTED_ABS
    SELECTED_ABS="$(realpath -e -- "$SELECTED" 2>/dev/null)" || {
        printf 'Cannot resolve selected file path.\n' >&2
        return 1
    }

    local TMP_DIR
    TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/open-file.XXXXXXXX")" || {
        printf 'Could not create temporary directory.\n' >&2
        return 1
    }
    chmod 700 "$TMP_DIR"

    local TMP_COPY="$TMP_DIR/original.${EXT}"
    local PNG="$TMP_DIR/converted.png"

    if ! cp -- "$SELECTED_ABS" "$TMP_COPY"; then
        printf 'Could not copy original; original preserved.\n' >&2
        rm -rf -- "$TMP_DIR"
        return 1
    fi

    if "$IM_CMD" "${TMP_COPY}[0]" \
        -define png:compression-level=0 "$PNG" \
        >/dev/null 2>&1 &&
        [[ -s "$PNG" ]] &&
        "$IM_CMD" identify "$PNG" >/dev/null 2>&1; then

        echo "Opening File [${NAME}]..."
        zathura -- "$PNG" >/dev/null 2>&1 &
        local ZATHURA_PID=$!
        wait "$ZATHURA_PID" 2>/dev/null || true

        rm -rf -- "$TMP_DIR"
        return 0
    else
        printf 'Conversion failed; original preserved.\n' >&2
        rm -rf -- "$TMP_DIR"
        open_file "$SELECTED"
        return 0
    fi
}

# ---------- Argument handling ----------
if [[ $# -ge 1 && -f "$1" ]]; then
    # Direct file mode: zt picture.jpg  or  zt file_without_ext
    open_selected "$1"
    exit $?
fi

# Directory / interactive mode
SEARCH_DIR="${1:-.}"

FILES=()
while IFS= read -r -d '' file; do
    name="${file##*/}"
    [[ "$name" == *.* ]] || continue

    ext="${name##*.}"
    ext="${ext,,}"

    if [[ -n "${ALLOWED_SET[$ext]+yes}" ]]; then
        FILES+=("$file")
    fi
done < <(find "$SEARCH_DIR" -maxdepth 1 -type f -print0 2>/dev/null)

if ((${#FILES[@]} == 0)); then
    printf 'No supported files found in: %s\n' "$SEARCH_DIR"
    exit 0
fi

# ---------- Interactive selection ----------
selected=0
offset=0
header_lines=2
height=$(( $(tput lines) - header_lines - 2 ))
(( height < 5 )) && height=10
(( height > ${#FILES[@]} )) && height=${#FILES[@]}
menu_lines=$(( height + header_lines ))

tput civis

_draw() {
    local i end=$(( offset + height ))
    (( end > ${#FILES[@]} )) && end=${#FILES[@]}

    printf "Select file (↑/↓, Enter to open, q to cancel)\n\n"
    for (( i=offset; i<end; i++ )); do
        if (( i == selected )); then
            printf "  \e[7m %s \e[0m\n" "${FILES[i]##*/}"
        else
            printf "    %s\n" "${FILES[i]##*/}"
        fi
    done
}

_draw

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
                (( selected < ${#FILES[@]}-1 )) && ((selected++))
                (( selected >= offset + height )) && ((offset++))
                ;;
            '[5') # Page Up
                (( selected -= height ))
                (( selected < 0 )) && selected=0
                (( offset = selected ))
                ;;
            '[6') # Page Down
                (( selected += height ))
                (( selected >= ${#FILES[@]} )) && selected=$((${#FILES[@]}-1))
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
        exit 0
    fi

    tput cuu $menu_lines
    tput ed
    _draw
done

# Clear only the menu
tput cuu $menu_lines
tput ed
tput cnorm

open_selected "${FILES[selected]}"
