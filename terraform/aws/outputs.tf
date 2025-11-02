output "instance_ids" {
  description = "Map of hostname to instance ID"
  value       = { for k, v in aws_instance.splunk : k => v.id }
}

output "public_ips" {
  description = "Map of hostname to public IP address"
  value       = { for k, v in aws_instance.splunk : k => v.public_ip }
}

output "private_ips" {
  description = "Map of hostname to private IP address"
  value       = { for k, v in aws_instance.splunk : k => v.private_ip }
}
