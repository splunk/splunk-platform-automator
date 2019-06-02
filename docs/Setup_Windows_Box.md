# Setup Windows Vagrant image

## Install and configure Windows in VirtualBox

Create a VirtualBox machine and install Windows 10 in it. Here we call it `Windows 10 (Vagrant Template)`. Follow the next steps to configure it for Vagrant use.

## Ansible on Windows runs over WinRM

Configure WinRM on the staging Windows host

Run this in the PowerShell as Administrator:

```
Enable-PSRemoting -SkipNetworkProfileCheck -Force
Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Force
```

Set some WinRM settings in cmd.exe as Administrator:

```
winrm set winrm/config @{MaxTimeoutms="1800000"}
winrm set winrm/config/service @{AllowUnencrypted="true"}
winrm set winrm/config/service/auth @{Basic="true"}
```

## Create the windows virtualBox image

Package the image

```
vagrant package --base "Windows 10 (Vagrant Template)" --output /var/tmp/windows.box --vagrantfile Vagrant/Splunkenizer/template/Vagrantfile_windows
```

Add the new Windows image to vagrant
```
vagrant box add /var/tmp/windows.box --name windows/10 --box-version 20190505.01
```
