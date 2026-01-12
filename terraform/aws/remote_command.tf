# Remote command execution (only created if remote_command is defined)
resource "null_resource" "remote_command" {
  for_each = var.remote_command != "" ? aws_instance.splunk : {}

  triggers = {
    instance_id = each.value.id
  }

  provisioner "remote-exec" {
    inline = [var.remote_command]

    connection {
      type        = "ssh"
      user        = local.ssh_username
      private_key = file(var.ssh_private_key_file)
      host        = each.value.public_ip
      timeout     = "5m"
    }
  }

  depends_on = [null_resource.wait_for_status_checks]
}
