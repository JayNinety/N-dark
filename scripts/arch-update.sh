#/bin/bash!

echo "Arch Linux update inicialized...
"
sudo pacman -Sy >> /dev/null
sudo pacman -Syu

#delete shortcuts automatically:
sudo rm /usr/share/applications/avahi-discover.desktop
sudo rm /usr/share/applications/bvnc.desktop
sudo rm /usr/share/applications/foot-server.desktop
sudo rm /usr/share/applications/xgps.desktop
sudo rm /usr/share/applications/footclient.desktop
sudo rm /usr/share/applications/bssh.desktop
sudo rm /usr/share/applications/xgpsspeed.desktop
sudo rm /usr/share/applications/qv4l2.desktop
sudo rm /usr/share/applications/qvidcap.desktop
sudo rm /usr/share/applications/org.pwmt.zathura.desktop

echo "
Update finished!
"

