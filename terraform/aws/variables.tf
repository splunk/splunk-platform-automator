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

variable "security_group_names" {
  type    = list(string)
  default = ["Splunk_Basic"]
}

variable "host_configs" {
  type = map(object({
    instance_type = optional(string, "t2.micro")
    root_volume_size = optional(number, 50)
    root_volume_type = optional(string, "gp3")
    additional_tags = optional(map(string), {})
  }))
  description = "Per-host configurations including storage and instance settings"
  default = {}
}

variable "security_group_ids" {
  type    = list(string)
  default = ["Splunk_Basic"]
}

variable "tags" {
  type = map(string)
  default = {
    splunkit_data_classification = "public"
    splunkit_environment_type   = "non-prd"
  }
}
