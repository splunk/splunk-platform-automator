---
description: Deploy Splunk infrastructure to AWS using Terraform
---

# Deploy Splunk Infrastructure to AWS with Terraform

This workflow provisions AWS infrastructure using Terraform and deploys Splunk.

## Prerequisites

1. **AWS Credentials**: Set environment variables or configure in `config/splunk_config.yml`
   ```bash
   export AWS_ACCESS_KEY_ID="your-access-key"
   export AWS_SECRET_ACCESS_KEY="your-secret-key"
   ```

2. **Terraform**: Ensure Terraform 1.3.0+ is installed
   ```bash
   terraform --version
   ```

3. **Ansible Collection**: Install community.general collection
   ```bash
   ansible-galaxy collection install community.general
   ```

4. **AWS Resources**: Ensure these exist in your AWS account:
   - Security group (e.g., "Splunk_Basic")
   - EC2 key pair
   - AMI ID for your region

## Step 1: Configure Infrastructure

Edit `config/splunk_config.yml` and add/update the `terraform.aws` section:

```yaml
terraform:
  aws:
    region: "eu-central-1"
    ami_id: "ami-03cbad7144aeda3eb"  # Redhat 9
    key_name: "aws_key"
    ssh_private_key_file: "~/.ssh/aws_key.pem"
    ssh_username: "ec2-user"
    security_group_names: ["Splunk_Basic"]
    instance_type: "t2.micro"
    root_volume_size: 50
```

## Step 2: Preview Infrastructure Changes

Generate Terraform configuration and preview what will be created:

// turbo
```bash
ansible-playbook ansible/provision_terraform_aws.yml --tags plan
```

This will:
- Generate `terraform/aws/terraform.tfvars`
- Run `terraform init`
- Run `terraform plan` and show you what will be created
- NOT apply any changes

## Step 3: Provision Infrastructure

Apply the Terraform configuration to create AWS resources:

```bash
ansible-playbook ansible/provision_terraform_aws.yml
```

This will:
1. Generate Terraform configuration
2. Initialize Terraform
3. Show you the plan
4. **Prompt for confirmation** before applying
5. Create EC2 instances
6. Generate `inventory/hosts` file
7. **Wait for SSH to be available** on all hosts (default behavior)

**To skip confirmation** (auto-approve):
```bash
ansible-playbook ansible/provision_terraform_aws.yml -e auto_approve=true
```

**To skip SSH wait** (not recommended):
```bash
ansible-playbook ansible/provision_terraform_aws.yml -e wait_for_ssh=false
```

## Step 4: Verify Host Readiness (Optional but Recommended)

Run comprehensive readiness checks on all provisioned hosts:

// turbo
```bash
ansible-playbook ansible/wait_for_terraform_aws_hosts.yml
```

This playbook performs:
- ✅ SSH port availability check
- ✅ SSH authentication test
- ✅ Python availability verification
- ✅ System uptime check
- ✅ Cloud-init completion check (if applicable)

**Expected output:**
```
TASK [Display success message]
ok: [localhost] => {
    "msg": "✅ All 5 hosts are ready for Ansible provisioning!\n\nYou can now run:\n  ansible-playbook ansible/deploy_site.yml\n"
}
```

## Step 5: Deploy Splunk

Once hosts are ready, deploy Splunk software:

```bash
ansible-playbook ansible/deploy_site.yml
```

This will:
- Install Splunk Enterprise/Forwarders
- Configure all roles (indexers, search heads, etc.)
- Set up clustering if configured
- Apply base configuration apps

## Step 6: Verify Deployment

Check the generated link page for access to Splunk instances:

```bash
open config/index.html
```

Or regenerate it:
```bash
ansible-playbook ansible/create_linkpage.yml
```

## Troubleshooting

### Hosts not ready after provisioning

If Step 3 completes but hosts aren't ready:

1. Check SSH connectivity manually:
   ```bash
   ssh -i ~/.ssh/aws_key.pem ec2-user@<public_ip>
   ```

2. Run the wait playbook with verbose output:
   ```bash
   ansible-playbook ansible/wait_for_terraform_aws_hosts.yml -v
   ```

3. Check AWS console for instance status

### SSH timeout errors

If you see "SSH port 22 not available" errors:

1. Verify security group allows SSH (port 22) from your IP
2. Verify the EC2 key pair is correct
3. Check if instances are in "running" state in AWS console
4. Increase timeout (default is 300 seconds):
   ```bash
   ansible-playbook ansible/wait_for_terraform_aws_hosts.yml -e ssh_timeout=600
   ```

### Terraform state issues

If Terraform complains about state:

```bash
cd terraform/aws
terraform state list
terraform refresh
```

## Cleanup

To destroy all AWS resources:

```bash
ansible-playbook ansible/destroy_terraform_aws.yml
```

**Warning:** This will permanently delete all EC2 instances and associated resources!

## Quick Reference

| Command | Purpose |
|---------|---------|
| `ansible-playbook ansible/provision_terraform_aws.yml --tags plan` | Preview changes only |
| `ansible-playbook ansible/provision_terraform_aws.yml` | Provision infrastructure |
| `ansible-playbook ansible/wait_for_terraform_aws_hosts.yml` | Verify host readiness |
| `ansible-playbook ansible/deploy_site.yml` | Deploy Splunk |
| `ansible-playbook ansible/destroy_terraform_aws.yml` | Destroy infrastructure |
| `ansible-inventory --list` | View current inventory |

## Advanced Options

### Skip SSH wait during provisioning
```bash
ansible-playbook ansible/provision_terraform_aws.yml -e wait_for_ssh=false
```

### Custom SSH timeout
```bash
ansible-playbook ansible/wait_for_terraform_aws_hosts.yml -e ssh_timeout=600
```

### Deploy to specific hosts only
```bash
ansible-playbook ansible/deploy_site.yml --limit idx1,idx2
```

### Rerun provisioning on existing hosts
```bash
ansible-playbook ansible/deploy_site.yml --limit idx1
```
