terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Lookup security group IDs from names
data "aws_security_groups" "selected" {
  filter {
    name   = "group-name"
    values = var.security_group_names
  }
}

# Use the configured SSH username directly
locals {
  ssh_username = var.ssh_username
}

resource "aws_instance" "splunk" {
  for_each               = var.host_configs
  ami                    = var.ami_id
  instance_type          = each.value.instance_type
  key_name               = var.key_name
  vpc_security_group_ids = data.aws_security_groups.selected.ids

  # Enable detailed monitoring for better visibility
  monitoring = true

  # Safety: stop instead of terminate on shutdown
  instance_initiated_shutdown_behavior = "stop"

  # User data to ensure cloud-init completion
  user_data = <<-EOF
    #!/bin/bash
    # Wait for cloud-init to complete
    cloud-init status --wait
    
    # Create completion marker
    touch /var/lib/cloud/instance/boot-finished
    
    # Log completion
    echo "Instance initialization complete at $(date)" >> /var/log/cloud-init-complete.log
  EOF

  root_block_device {
    volume_type           = each.value.root_volume_type
    volume_size           = each.value.root_volume_size
    encrypted             = each.value.root_volume_encrypted
    delete_on_termination = true
  }

  dynamic "ebs_block_device" {
    for_each = each.value.additional_volumes
    content {
      device_name           = ebs_block_device.value.device_name
      volume_type           = ebs_block_device.value.volume_type
      volume_size           = ebs_block_device.value.volume_size
      encrypted             = ebs_block_device.value.encrypted
      delete_on_termination = ebs_block_device.value.delete_on_termination
    }
  }

  tags = merge(
    var.tags,
    { "Name" = each.key },
    each.value.additional_tags
  )
}
