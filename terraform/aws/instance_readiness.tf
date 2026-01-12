# Wait for instances to pass AWS status checks
# This ensures instances are fully ready before Ansible deployment

resource "null_resource" "wait_for_status_checks" {
  for_each = aws_instance.splunk

  # Trigger on instance changes
  triggers = {
    instance_id = each.value.id
  }

  # Use AWS CLI to wait for both instance and system status checks to pass
  provisioner "local-exec" {
    command = <<-EOT
      echo "Waiting for instance ${each.key} (${each.value.id}) to pass status checks..."
      aws ec2 wait instance-status-ok --instance-ids ${each.value.id} --region ${var.aws_region}
      echo "✅ Instance ${each.key} is ready"
    EOT
  }

  depends_on = [aws_instance.splunk]
}
