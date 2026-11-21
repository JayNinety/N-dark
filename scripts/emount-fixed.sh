#!/usr/bin/env bash

# ============================================================
#  Device Mount Manager
#
#  Mounts removable/storage partitions under:
#      /run/media/jay/<DeviceLabel>
#
#  Features:
#    - List physical storage devices
#    - Select device
#    - Select partition
#    - Mount partition
#    - Give current user read/write access
#    - List mounted partitions
#    - Unmount partition
#    - Remove mount directory after unmount
#
#  Tested conceptually with:
#    ext2/ext3/ext4
#    btrfs
#    xfs
#    vfat/FAT32
#    exFAT
#    NTFS/NTFS3
# ============================================================

set -u

# Resolve the actual desktop user even if invoked with sudo.
USER_NAME="${SUDO_USER:-$(id -un)}"
USER_UID="$(id -u "$USER_NAME")"
USER_GID="$(id -g "$USER_NAME")"

MOUNT_BASE="/run/media/$USER_NAME"

# ------------------------------------------------------------
# Colors
# ------------------------------------------------------------

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------

pause() {
    echo
    read -rp "Press Enter to continue..."
}

error() {
    echo -e "${RED}ERROR:${NC} $*" >&2
}

success() {
    echo -e "${GREEN}$*${NC}"
}

warning() {
    echo -e "${YELLOW}$*${NC}"
}

info() {
    echo -e "${CYAN}$*${NC}"
}

# ------------------------------------------------------------
# Check dependencies
# ------------------------------------------------------------

check_dependencies() {

    local commands=(
        lsblk
        findmnt
        mount
        umount
        sudo
    )

    for command in "${commands[@]}"; do
        if ! command -v "$command" >/dev/null 2>&1; then
            error "Required command not found: $command"
            exit 1
        fi
    done
}

# ------------------------------------------------------------
# Create mount directory
# ------------------------------------------------------------

create_mount_base() {

    if [[ ! -d "$MOUNT_BASE" ]]; then
        sudo mkdir -p "$MOUNT_BASE"
        sudo chown "$USER_UID:$USER_GID" "$MOUNT_BASE"
    fi
}

# ------------------------------------------------------------
# Sanitize filesystem label
#
# Converts things like:
#   "My USB Drive" -> "My_USB_Drive"
#
# This also prevents / from becoming part of the path.
# ------------------------------------------------------------

sanitize_label() {

    local label="$1"

    label="${label//\//_}"
    label="${label// /_}"

    # Remove characters that are problematic in a path.
    label="$(printf '%s' "$label" | tr -cd '[:alnum:]_.-')"

    # Avoid an empty directory name.
    if [[ -z "$label" ]]; then
        label="Storage"
    fi

    printf '%s' "$label"
}

# ------------------------------------------------------------
# Generate mount point
# ------------------------------------------------------------

get_mount_point() {

    local partition="$1"
    local label

    label="$(lsblk -dnro LABEL "$partition" 2>/dev/null || true)"

    if [[ -z "$label" ]]; then
        label="$(basename "$partition")"
    fi

    label="$(sanitize_label "$label")"

    local mount_point="$MOUNT_BASE/$label"

    # If a mount directory with the same label already exists,
    # avoid accidentally using an existing directory for another
    # partition.
    if [[ -e "$mount_point" ]]; then

        local current_source

        current_source="$(findmnt -rn -S "$partition" -o TARGET 2>/dev/null || true)"

        if [[ -n "$current_source" ]]; then
            printf '%s' "$current_source"
            return
        fi

        local counter=2

        while [[ -e "${mount_point}_${counter}" ]]; do
            ((counter++))
        done

        mount_point="${mount_point}_${counter}"
    fi

    printf '%s' "$mount_point"
}

# ------------------------------------------------------------
# Display disks
# ------------------------------------------------------------

list_disks() {

    mapfile -t DISKS < <(
        lsblk -dnpo NAME,TYPE |
        awk '$2 == "disk" {print $1}'
    )

    if [[ ${#DISKS[@]} -eq 0 ]]; then
        error "No storage devices found."
        return 1
    fi

    echo
    echo "============================================================"
    echo " Storage Devices"
    echo "============================================================"

    local i=1

    for disk in "${DISKS[@]}"; do

        local size model transport

        size="$(lsblk -dnro SIZE "$disk")"
        model="$(lsblk -dnro MODEL "$disk")"
        transport="$(lsblk -dnro TRAN "$disk")"

        [[ -z "$model" ]] && model="Unknown"

        printf " [%d] %-10s %-8s %-25s %s\n" \
            "$i" \
            "$disk" \
            "$size" \
            "$model" \
            "$transport"

        ((i++))
    done

    echo " [q] Cancel"
    echo
}

# ------------------------------------------------------------
# Select disk
# ------------------------------------------------------------

select_disk() {

    list_disks || return 1

    local choice

    while true; do

        read -rp "Which device do you want to inspect? [1-${#DISKS[@]}]: " choice

        if [[ "$choice" == "q" || "$choice" == "Q" ]]; then
            return 1
        fi

        if [[ "$choice" =~ ^[0-9]+$ ]] &&
           (( choice >= 1 && choice <= ${#DISKS[@]} )); then

            SELECTED_DISK="${DISKS[$((choice - 1))]}"
            return 0
        fi

        error "Invalid selection."
    done
}

# ------------------------------------------------------------
# List partitions on selected disk
# ------------------------------------------------------------

list_partitions() {

    local disk="$1"

    mapfile -t PARTITIONS < <(
        lsblk -nrpo NAME,TYPE "$disk" |
        awk '$2 == "part" {print $1}'
    )

    if [[ ${#PARTITIONS[@]} -eq 0 ]]; then
        error "No partitions found on $disk."
        return 1
    fi

    echo
    echo "============================================================"
    echo " Partitions on $disk"
    echo "============================================================"

    local i=1

    for partition in "${PARTITIONS[@]}"; do

        local size fstype label mountpoint

        size="$(lsblk -dnro SIZE "$partition")"
        fstype="$(lsblk -dnro FSTYPE "$partition")"
        label="$(lsblk -dnro LABEL "$partition")"
        mountpoint="$(lsblk -dnro MOUNTPOINTS "$partition")"

        [[ -z "$fstype" ]] && fstype="unknown"
        [[ -z "$label" ]] && label="-"
        [[ -z "$mountpoint" ]] && mountpoint="-"

        printf " [%d] %-12s %-8s %-10s %-20s %s\n" \
            "$i" \
            "$partition" \
            "$size" \
            "$fstype" \
            "$label" \
            "$mountpoint"

        ((i++))
    done

    echo " [q] Cancel"
    echo
}

# ------------------------------------------------------------
# Select partition
# ------------------------------------------------------------

select_partition() {

    local disk="$1"

    list_partitions "$disk" || return 1

    local choice

    while true; do

        read -rp "Which partition do you want to mount? [1-${#PARTITIONS[@]}]: " choice

        if [[ "$choice" == "q" || "$choice" == "Q" ]]; then
            return 1
        fi

        if [[ "$choice" =~ ^[0-9]+$ ]] &&
           (( choice >= 1 && choice <= ${#PARTITIONS[@]} )); then

            SELECTED_PARTITION="${PARTITIONS[$((choice - 1))]}"
            return 0
        fi

        error "Invalid selection."
    done
}

# ------------------------------------------------------------
# Check if partition is already mounted
# ------------------------------------------------------------

is_mounted() {

    local partition="$1"

    findmnt -rn -S "$partition" >/dev/null 2>&1
}

# ------------------------------------------------------------
# Get filesystem type
# ------------------------------------------------------------

get_fstype() {

    local partition="$1"

    lsblk -dnro FSTYPE "$partition" 2>/dev/null
}

# ------------------------------------------------------------
# Apply permissions
# ------------------------------------------------------------

set_user_permissions() {

    local partition="$1"
    local mount_point="$2"
    local fstype="$3"

    echo
    info "Configuring permissions for $USER_NAME..."

    case "$fstype" in

        # ----------------------------------------------------
        # FAT filesystems
        #
        # FAT does not store normal Linux ownership.
        # uid/gid/umask are therefore the correct mechanism.
        # ----------------------------------------------------

        vfat|msdos|fat)
            success "FAT filesystem detected."

            # Already mounted by this point, so ownership is
            # determined by mount options. Nothing recursive
            # is necessary.
            return 0
            ;;

        # ----------------------------------------------------
        # exFAT
        # ----------------------------------------------------

        exfat)
            success "exFAT filesystem detected."
            return 0
            ;;

        # ----------------------------------------------------
        # NTFS
        # ----------------------------------------------------

        ntfs|ntfs3)
            success "NTFS filesystem detected."
            return 0
            ;;

        # ----------------------------------------------------
        # Linux filesystems supporting POSIX ACLs
        # ----------------------------------------------------

        ext2|ext3|ext4|xfs|btrfs|f2fs|jfs)
            if ! command -v setfacl >/dev/null 2>&1; then
                warning "setfacl is not installed."
                warning "Install the 'acl' package to enable ACL permissions."
                return 1
            fi

            echo "Applying ACLs to existing files and directories..."

            # Existing files:
            #   user gets read/write
            #
            # Existing directories:
            #   user gets read/write/execute
            #
            # rwX means execute is added to directories and to
            # files that already have execute permission.
            sudo setfacl -R -m "u:$USER_NAME:rwX" "$mount_point"

            # Default ACL for newly created files/directories.
            #
            # This makes future content accessible to the user
            # without needing sudo.
            sudo find "$mount_point" -type d -exec \
                setfacl -m "d:u:$USER_NAME:rwx" {} + 2>/dev/null

            success "ACL permissions configured."
            return 0
            ;;

        # ----------------------------------------------------
        # Unknown filesystem
        # ----------------------------------------------------

        *)
            warning "Filesystem '$fstype' is not specifically supported."
            warning "Attempting normal ACL permissions..."

            if command -v setfacl >/dev/null 2>&1; then
                sudo setfacl -R -m "u:$USER_NAME:rwX" "$mount_point" \
                    2>/dev/null || true

                sudo find "$mount_point" -type d -exec \
                    setfacl -m "d:u:$USER_NAME:rwx" {} + \
                    2>/dev/null || true

                success "ACL attempt completed."
            else
                warning "setfacl is not installed."
            fi
            ;;
    esac
}

# ------------------------------------------------------------
# Mount partition
# ------------------------------------------------------------

mount_partition() {

    local partition="$1"

    echo

    if is_mounted "$partition"; then
        error "$partition is already mounted."

        local existing_mount
        existing_mount="$(findmnt -rn -S "$partition" -o TARGET)"

        echo "Mounted at: $existing_mount"
        return 1
    fi

    local fstype
    fstype="$(get_fstype "$partition")"

    if [[ -z "$fstype" ]]; then
        error "Unable to determine filesystem type."
        return 1
    fi

    local mount_point
    mount_point="$(get_mount_point "$partition")"

    echo "Partition : $partition"
    echo "Filesystem: $fstype"
    echo "Mount at  : $mount_point"
    echo

    if ! sudo mkdir -p "$mount_point"; then
        error "Unable to create mount directory: $mount_point"
        return 1
    fi

    # --------------------------------------------------------
    # Mount options
    #
    # For filesystems that don't store Linux ownership:
    #
    # uid = current user
    # gid = current user's group
    #
    # fmask=0000 -> files readable/writable
    # dmask=0000 -> directories readable/writable/searchable
    #
    # We use 0002 instead of 0000 so "other" users don't
    # automatically get write access.
    # --------------------------------------------------------

    local mount_options="rw"
    local mount_type="$fstype"

    case "$fstype" in

        vfat|msdos|fat|exfat)
            mount_options="rw,uid=$USER_UID,gid=$USER_GID,umask=0002"
            ;;

        ntfs|ntfs3)
            # Explicitly choose the FUSE ntfs-3g driver: auto-detection
            # may select the kernel ntfs3 driver, which failed previously.
            if ! command -v mount.ntfs-3g >/dev/null 2>&1 &&
               ! command -v ntfs-3g >/dev/null 2>&1; then
                error "ntfs-3g is missing. Install it first (Arch: sudo pacman -S ntfs-3g)."
                sudo rmdir "$mount_point" 2>/dev/null || true
                return 1
            fi
            mount_type="ntfs-3g"
            mount_options="rw,uid=$USER_UID,gid=$USER_GID,umask=0002"
            ;;

        udf)
            mount_options="rw,uid=$USER_UID,gid=$USER_GID,umask=0002"
            ;;

        *)
            mount_options="rw"
            ;;
    esac

    echo "Mount driver : $mount_type"
    echo "Mount options: $mount_options"
    echo

    if ! sudo mount -t "$mount_type" -o "$mount_options" \
        "$partition" "$mount_point"; then

        error "Mount failed."

        # Remove directory if it was created by us and is empty.
        sudo rmdir "$mount_point" 2>/dev/null || true

        return 1
    fi

    # Do not chown the mounted filesystem root: UID/GID mount options
    # already provide ownership on NTFS/FAT/exFAT, and chown would
    # unexpectedly modify real ownership on native Linux filesystems.

    success "Mounted successfully:"
    echo
    echo "  $partition"
    echo "      ->"
    echo "  $mount_point"

    # --------------------------------------------------------
    # For native Linux filesystems, apply ACLs.
    #
    # For FAT/exFAT/NTFS, UID/GID mount options already give
    # the user ownership-like access.
    # --------------------------------------------------------

    case "$fstype" in
        vfat|msdos|fat|exfat|ntfs|ntfs3|udf)
            success "User permissions provided through mount options."
            ;;

        *)
            set_user_permissions "$partition" "$mount_point" "$fstype"
            ;;
    esac

    echo
    if [[ "$fstype" == ntfs || "$fstype" == ntfs3 ]]; then
        if ! sudo -u "$USER_NAME" test -w "$mount_point"; then
            warning "NTFS mounted, but $USER_NAME does not have write access."
            warning "Check for Windows hibernation, Fast Startup or NTFS errors."
            return 1
        fi
    fi
    success "The partition is ready for normal user access."
}

# ------------------------------------------------------------
# Mount menu
# ------------------------------------------------------------

mount_menu() {

    if ! select_disk; then
        return
    fi

    echo
    info "Selected device: $SELECTED_DISK"

    if ! select_partition "$SELECTED_DISK"; then
        return
    fi

    echo
    info "Selected partition: $SELECTED_PARTITION"

    mount_partition "$SELECTED_PARTITION"

    pause
}

# ------------------------------------------------------------
# List mounted partitions
# ------------------------------------------------------------

list_mounted() {

    local mounted

    mounted="$(
        findmnt -rn -o SOURCE,TARGET,FSTYPE |
        awk -v base="$MOUNT_BASE" '
            index($2, base "/") == 1 {
                print
            }
        '
    )"

    echo
    echo "============================================================"
    echo " Mounted Partitions"
    echo "============================================================"

    if [[ -z "$mounted" ]]; then
        echo
        echo " No partitions mounted by this script."
        return 1
    fi

    echo
    printf "%-15s %-45s %-10s\n" "DEVICE" "MOUNT POINT" "FILESYSTEM"
    echo "--------------------------------------------------------------------------"

    while read -r source target fstype; do
        printf "%-15s %-45s %-10s\n" \
            "$source" \
            "$target" \
            "$fstype"
    done <<< "$mounted"

    echo
    return 0
}

# ------------------------------------------------------------
# Get mounted partitions into arrays
# ------------------------------------------------------------

get_mounted_partitions() {

    mapfile -t MOUNTED_PARTITIONS < <(
        findmnt -rn -o SOURCE,TARGET |
        awk -v base="$MOUNT_BASE" '
            index($2, base "/") == 1 {
                print $1 "|" $2
            }
        '
    )
}

# ------------------------------------------------------------
# Unmount partition
# ------------------------------------------------------------

unmount_partition() {

    local source="$1"
    local mount_point="$2"

    echo
    echo "Unmounting:"
    echo "  Device: $source"
    echo "  Path  : $mount_point"
    echo

    if sudo umount "$mount_point"; then

        success "Unmounted successfully."

        # Only remove the directory if it is now empty.
        if sudo rmdir "$mount_point" 2>/dev/null; then
            success "Removed mount directory: $mount_point"
        else
            warning "Could not remove $mount_point."
            warning "The directory may not be empty or may not be owned by this script."
        fi

    else
        error "Could not unmount $mount_point."

        echo
        echo "If something is using the directory, check with:"
        echo
        echo "    sudo lsof +D \"$mount_point\""
        echo
        echo "or:"
        echo
        echo "    sudo fuser -vm \"$mount_point\""
    fi
}

# ------------------------------------------------------------
# Unmount menu
# ------------------------------------------------------------

unmount_menu() {

    get_mounted_partitions

    if [[ ${#MOUNTED_PARTITIONS[@]} -eq 0 ]]; then
        echo
        echo "No mounted partitions found under:"
        echo "  $MOUNT_BASE"
        echo
        pause
        return
    fi

    echo
    echo "============================================================"
    echo " Select Partition to Unmount"
    echo "============================================================"

    local i=1

    for entry in "${MOUNTED_PARTITIONS[@]}"; do

        local source="${entry%%|*}"
        local target="${entry#*|}"

        printf " [%d] %-15s -> %s\n" \
            "$i" \
            "$source" \
            "$target"

        ((i++))
    done

    echo " [q] Cancel"
    echo

    local choice

    while true; do

        read -rp "Which partition do you want to unmount? [1-${#MOUNTED_PARTITIONS[@]}]: " choice

        if [[ "$choice" == "q" || "$choice" == "Q" ]]; then
            return
        fi

        if [[ "$choice" =~ ^[0-9]+$ ]] &&
           (( choice >= 1 && choice <= ${#MOUNTED_PARTITIONS[@]} )); then

            local selected="${MOUNTED_PARTITIONS[$((choice - 1))]}"

            local source="${selected%%|*}"
            local target="${selected#*|}"

            unmount_partition "$source" "$target"

            pause
            return
        fi

        error "Invalid selection."
    done
}

# ------------------------------------------------------------
# Show device information
# ------------------------------------------------------------

device_information() {

    if ! select_disk; then
        return
    fi

    echo
    echo "============================================================"
    echo " Device Information"
    echo "============================================================"
    echo

    lsblk -o NAME,PATH,SIZE,FSTYPE,LABEL,UUID,FSAVAIL,FSUSE%,MOUNTPOINTS \
        "$SELECTED_DISK"

    echo
    pause
}

# ------------------------------------------------------------
# Main menu
# ------------------------------------------------------------

main_menu() {

    while true; do

        clear

        echo
        echo "============================================================"
        echo "             Device Mount Manager"
        echo "============================================================"
        echo
        echo " User       : $USER_NAME"
        echo " Mount base : $MOUNT_BASE"
        echo
        echo " [1] Mount a partition"
        echo " [2] Unmount a partition"
        echo " [3] List mounted partitions"
        echo " [4] List storage devices"
        echo " [5] Device information"
        echo " [6] Refresh / Main menu"
        echo " [q] Quit"
        echo
        echo "============================================================"
        echo

        local choice

        read -rp "Choose an option: " choice

        case "$choice" in

            1)
                mount_menu
                ;;

            2)
                unmount_menu
                ;;

            3)
                list_mounted
                pause
                ;;

            4)
                list_disks
                pause
                ;;

            5)
                device_information
                ;;

            6)
                continue
                ;;

            q|Q)
                echo
                echo "Goodbye."
                exit 0
                ;;

            *)
                error "Invalid option."
                sleep 1
                ;;
        esac
    done
}

# ------------------------------------------------------------
# Program start
# ------------------------------------------------------------

check_dependencies
create_mount_base
main_menu
