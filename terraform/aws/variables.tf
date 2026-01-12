variable "aws_region" {
  type    = string
  default = "eu-central-1"
}

variable "instance_type" {
  type    = string
  default = "t2.micro"
}

variable "ami_id" {
  type    = string
  default = "ami-01a612f2c60d80101"
}

variable "key_name" {
  type    = string
  default = "aws_key"
}

variable "ssh_username" {
  type        = string
  default     = "ubuntu"
  description = "SSH username for connecting to instances"
}

variable "ssh_private_key_file" {
  type        = string
  default     = "~/.ssh/aws_key.pem"
  description = "Path to SSH private key file for connecting to instances"
}

variable "security_group_names" {
  type    = list(string)
  default = ["Splunk_Basic"]
}

variable "host_configs" {
  type = map(object({
    instance_type         = optional(string, "t2.micro")
    root_volume_size      = optional(number, 50)
    root_volume_type      = optional(string, "gp3")
    root_volume_encrypted = optional(bool, true)
    additional_tags       = optional(map(string), {})
    additional_volumes = optional(list(object({
      device_name           = string
      volume_size           = number
      volume_type           = optional(string, "gp3")
      encrypted             = optional(bool, true)
      delete_on_termination = optional(bool, true)
    })), [])
  }))
  description = "Per-host configurations including storage and instance settings"
  default     = {}
}

variable "security_group_ids" {
  type    = list(string)
  default = ["Splunk_Basic"]
}

variable "tags" {
  type = map(string)
  default = {
    Env = "Splunk Lab"
  }
}

variable "remote_command" {
  type        = string
  description = "Optional command to run on instances after creation via SSH"
  default     = ""
}
