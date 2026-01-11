# Ansible-Terraform Integration

## Overview

This integration allows you to provision AWS infrastructure using Terraform while maintaining a single source of truth in your `splunk_config.yml` file. An Ansible playbook automatically generates `terraform.tfvars` from your config and manages the Terraform lifecycle.

## Quick Start

### 1. Configure Your Infrastructure

Edit `config/splunk_config.yml` and add a `terraform` section:

```yaml
terraform:
  aws:
    region: 'eu-central-1'
    ami_id: 'ami-0badcc5b522737046'
    key_name: 'aws_key'
    ssh_private_key_file: '~/.ssh/aws_key.pem'
    security_group_names: ['Splunk_Basic']
    tags:
      Env: "Splunk Lab"

splunk_hosts:
  - name: idx1
    roles: [indexer]
    terraform:
      aws:
        instance_type: 't3.large'
        root_volume_size: 100
        additional_volumes:
          - device_name: "/dev/xvdb"
            volume_size: 500
```

### 2. Provision Infrastructure

```bash
cd ansible
ansible-playbook provision_aws_terraform.yml
```

This will:
1. Generate `terraform/aws/terraform.tfvars` from your config
2. Run `terraform init`
3. Run `terraform plan` and show you the changes
4. Prompt for confirmation
5. Apply the changes
6. Save `ansible_inventory.json` for subsequent playbooks

### 3. Use the Provisioned Infrastructure

The playbook captures Terraform outputs and makes them available to subsequent Ansible playbooks:

```bash
# Use the generated inventory
ansible-playbook -i ../ansible_inventory.json install_splunk.yml
```

### 4. Destroy Infrastructure

```bash
ansible-playbook destroy_aws_terraform.yml
```

## Configuration Structure

### Global Terraform Settings

```yaml
terraform:
  aws:
    region: 'eu-central-1'              # AWS region
    ami_id: 'ami-xxx'                   # AMI to use
    key_name: 'aws_key'                 # EC2 key pair name
    ssh_private_key_file: '~/.ssh/aws_key.pem'  # Path to private key
    security_group_names: ['Splunk_Basic']      # Security groups
    instance_type: 't2.micro'   # Default if not specified per host
    tags:                               # Tags applied to all instances
      Env: "Splunk Lab"
```

### Per-Host Terraform Settings

Add a `terraform.aws` section to any host in `splunk_hosts` to override global defaults:

```yaml
splunk_hosts:
  - name: idx1
    roles: [indexer]
    terraform:
      aws:
        instance_type: 't3.large'         # Instance type
        root_volume_size: 100             # Root volume size in GB
        root_volume_type: 'gp3'           # Volume type (default: gp3)
        root_volume_encrypted: true       # Encrypt root volume (default: true)
        
        additional_volumes:               # Optional additional EBS volumes
          - device_name: "/dev/xvdb"
            volume_size: 500
            volume_type: "gp3"
            encrypted: true
            delete_on_termination: true
        
        additional_tags:                  # Host-specific tags
          Role: "Indexer"
```

**How defaults work:**
- Global `terraform.aws` settings provide defaults
- Host-specific `terraform.aws` settings override global defaults
- If a host has no `terraform` section, it uses `terraform.aws.instance_type`

## Playbook Options

### Generate terraform.tfvars Only

```bash
ansible-playbook provision_aws_terraform.yml --tags generate
```

### Run Terraform Plan Only

```bash
ansible-playbook provision_aws_terraform.yml --tags plan
```

### Auto-Approve (Skip Confirmation)

```bash
ansible-playbook provision_aws_terraform.yml -e auto_approve=true
```

### View Outputs Only

```bash
ansible-playbook provision_aws_terraform.yml --tags outputs
```

## Files Created

- `terraform/aws/terraform.tfvars` - Generated Terraform variables
- `ansible_inventory.json` - Ansible inventory with connection details
- `terraform/aws/terraform.tfstate` - Terraform state (managed by Terraform)

## Examples

See `examples/splunk_config_terraform.yml` for a comprehensive example showing:
- Indexers with additional storage volumes
- Search heads with medium instances
- Universal forwarders with minimal configuration
- Hosts using default settings

## Migrating from block_device_mapping

**Old format (Ansible AWS):**
```yaml
aws:
  block_device_mapping:
    - DeviceName: "/dev/sdg"
      Ebs.VolumeSize: 500
```

**New format (Terraform):**
```yaml
terraform:
  aws:
    # ... global settings ...

splunk_hosts:
  - name: idx1
    terraform:
      aws:
        additional_volumes:
          - device_name: "/dev/xvdb"
            volume_size: 500
            volume_type: "gp3"
```

## Requirements

- Ansible 2.9+
- `community.general` collection (for terraform module)
- Terraform 1.3.0+
- AWS credentials configured

Install requirements:
```bash
ansible-galaxy collection install community.general
```

## Troubleshooting

### "terraform section is missing"
Ensure your `config/splunk_config.yml` has a `terraform.aws` section with required fields.

### "Module community.general.terraform not found"
Install the collection: `ansible-galaxy collection install community.general`

### Generated tfvars looks wrong
Run with `--tags generate` and check `terraform/aws/terraform.tfvars`

### Want to see Terraform output
The playbook displays Terraform plan output. For more details, run Terraform directly:
```bash
cd terraform/aws
terraform plan
```
