output "ansible_inventory" {
  description = "Ansible-compatible inventory in JSON format with all host details"
  value = jsonencode({
    for hostname, instance in aws_instance.splunk : hostname => {
      ansible_host                 = instance.public_dns
      ansible_user                 = local.ssh_username
      ansible_ssh_private_key_file = var.ssh_private_key_file
      private_dns_name             = instance.private_dns
      private_ip                   = instance.private_ip
      public_dns_name              = instance.public_dns
      public_ip                    = instance.public_ip
    }
  })
}
