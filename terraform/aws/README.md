# AWS Terraform Configuration for Splunk Infrastructure

This Terraform configuration provisions EC2 instances for Splunk deployments on AWS with encrypted storage and flexible per-host configurations.

## 📁 File Structure and Purpose

### Core Configuration Files

#### `main.tf` - **Infrastructure Definition** (⚠️ Modify with care)
**Purpose:** Defines the actual AWS resources to be created.

**Contains:**
- Terraform version requirements and provider configuration
- AWS provider setup with region configuration
- EC2 instance resource definition with:
  - Dynamic instance creation using `for_each` loop
  - Root and additional EBS volumes (encrypted by default)
  - Security group and network configuration
  - Tag management

**When to modify:**
- ✅ Adding new AWS resources (e.g., load balancers, S3 buckets)
- ✅ Changing EBS volume configurations (size, type, encryption)
- ✅ Modifying instance networking or storage architecture
- ❌ Changing instance types or AMIs (use `terraform.tfvars` instead)

---

#### `variables.tf` - **Variable Declarations** (⚠️ Modify defaults carefully)
**Purpose:** Declares all input variables with their types, descriptions, and default values.

**Contains:**
- `aws_region` - AWS region for deployment (default: eu-central-1)
- `ami_id` - Amazon Machine Image ID for instances
- `key_name` - SSH key pair name for instance access
- `security_group_names` - List of security groups to attach
- `host_configs` - Complex object for per-host configuration
  - `root_volume_encrypted` - Whether to encrypt root volume (default: true)
  - `additional_volumes` - List of optional additional EBS volumes (default: encrypted)
- `tags` - Common tags applied to all resources

**When to modify:**
- ✅ Changing default values for your environment
- ✅ Adding new variable declarations for additional configuration options
- ✅ Updating variable descriptions or validation rules
- ❌ Setting environment-specific values (use `terraform.tfvars` instead)

---

#### `terraform.tfvars` - **Your Configuration Values** (✅ **MODIFY THIS**)
**Purpose:** Contains your actual configuration values that override the defaults.

**This is the PRIMARY file you should edit** for:
- ✅ Specifying which instances to create and their names
- ✅ Setting instance types (t2.micro, t3.medium, etc.)
- ✅ Configuring storage sizes per instance
- ✅ Defining your AWS region, AMI ID, and SSH key
- ✅ Setting security groups and tags

**Example structure:**
```hcl
aws_region = "eu-central-1"
ami_id     = "ami-01a612f2c60d80101"
key_name   = "your-ssh-key"

host_configs = {
  "splunk-indexer-01" = {
    instance_type    = "t3.large"
    root_volume_size = 100
  }
  "splunk-search-head" = {
    instance_type    = "t3.medium"
    root_volume_size = 50
  }
}
```

> **Note:** This file is gitignored for security. Use `terraform.tfvars.example` as a template.

---

#### `outputs.tf` - **Output Values** (ℹ️ Reference only)
**Purpose:** Defines what information Terraform displays after deployment.

**Contains:**
- `instance_ids` - Map of hostname to AWS instance ID
- `public_ips` - Map of hostname to public IP addresses
- `private_ips` - Map of hostname to private IP addresses

**When to modify:**
- ✅ Adding new outputs (e.g., DNS names, volume IDs)
- ✅ Changing output formats or descriptions
- ❌ Rarely needs modification for basic usage

---

### Supporting Files

- **`.terraform.lock.hcl`** - Dependency lock file (auto-generated, commit to version control)
- **`terraform.tfstate`** - Current infrastructure state (auto-generated, **DO NOT EDIT**)
- **`terraform.tfstate.backup`** - Previous state backup (auto-generated)
- **`.terraform/`** - Provider plugins and modules (auto-generated)

---

## 🚀 Quick Start

### 1. Configure Your Environment

Copy the example configuration and customize it:
```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 2. Initialize Terraform

Download required providers:
```bash
terraform init
```

### 3. Preview Changes

See what will be created:
```bash
terraform plan
```

### 4. Deploy Infrastructure

Create the resources:
```bash
terraform apply
```

### 5. View Outputs

After deployment, Terraform displays instance IDs and IP addresses. Retrieve them anytime:
```bash
terraform output
```

---

## 🎯 Common Modification Scenarios

### Change Instance Type or Size
**File to edit:** `terraform.tfvars`
```hcl
host_configs = {
  "my-instance" = {
    instance_type    = "t3.large"  # Change this
    root_volume_size = 100         # Change this
  }
}
```

### Add a New Instance
**File to edit:** `terraform.tfvars`
```hcl
host_configs = {
  "existing-instance" = { ... }
  "new-instance" = {              # Add this block
    instance_type = "t3.medium"
  }
}
```

### Change AWS Region
**File to edit:** `terraform.tfvars`
```hcl
aws_region = "us-east-1"  # Change this
ami_id     = "ami-xxxxx"  # Update AMI for new region
```

### Add Additional EBS Volumes
**File to edit:** `terraform.tfvars`

Add the `additional_volumes` field to specify one or more EBS volumes:
```hcl
host_configs = {
  "splunk-indexer" = {
    instance_type = "t3.large"
    additional_volumes = [
      {
        device_name = "/dev/xvdb"
        volume_size = 100
        volume_type = "gp3"
      },
      {
        device_name = "/dev/xvdc"
        volume_size = 200
      }
    ]
  }
}
```

**Note:** Instances without `additional_volumes` specified will only have the root volume.

---

## ⚠️ Important Notes

- **Security Groups:** Ensure the security groups specified in `security_group_names` exist in your AWS account
- **SSH Keys:** The `key_name` must match an existing EC2 key pair in your AWS region
- **AMI IDs:** AMI IDs are region-specific; update when changing regions
- **State Files:** Never manually edit `terraform.tfstate` files
- **Credentials:** Ensure AWS credentials are configured via environment variables, AWS CLI, or IAM role

---

## 📚 Additional Resources

- [Terraform AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS EC2 Instance Types](https://aws.amazon.com/ec2/instance-types/)
- [Terraform Best Practices](https://www.terraform.io/docs/cloud/guides/recommended-practices/index.html)
