#!/bin/bash

echo "
Welcome!"
echo ""
echo "[1] Start Samba server"
echo "[2] Stop Samba server"
echo ""
read -p "What would you like to do? (1 or 2): " choice

case $choice in
    1)
        sudo systemctl start smb nmb
        echo ""
        echo "Server Running!"
        ;;
    2)
        sudo systemctl stop --now smb nmb
        echo ""
        echo "Server Stopped"
        ;;
    *)
        echo ""
        echo "Invalid option. Please choose 1 or 2."
        ;;
esac
