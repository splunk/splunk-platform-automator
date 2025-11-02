This Terraform configuration creates a single EC2 instance with the same hardcoded values used in the Ansible playbook.

Files:
- `main.tf`      - provider, data lookup for security group, and EC2 resource
- `variables.tf` - variables with defaults matching the Ansible values
- `outputs.tf`   - instance IDs and public IPs

Quick start

1. Ensure you have Terraform installed (>= 1.3.0) and AWS credentials available (environment, shared credentials file, or IAM role).

2. Initialize Terraform in this directory:

```bash
terraform init
```

3. (Optional) Preview the changes:

```bash
terraform plan
```

4. Apply to create the instance:

```bash
terraform apply
```

Notes
- The configuration looks up the security group by name in the given `vpc_id`. If the lookup fails, ensure the security group exists in that VPC.
- If you prefer to supply real values instead of the defaults, create a `terraform.tfvars` or pass `-var` on the CLI.
