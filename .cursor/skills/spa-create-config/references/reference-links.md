# Reference links — architecture and config design

Curated links for the `spa-create-config` workflow. Use for user handoff and header comments; do not paste full articles into configs.

## Splunk Validated Architectures (SVA)

- [About Splunk Validated Architectures](https://help.splunk.com/en/splunk-cloud-platform/splunk-validated-architectures/introduction-to-splunk-validated-architectures/about-splunk-validated-architectures)
- [Topology selection guidance (indexing and search)](https://help.splunk.com/en/splunk-enterprise/get-started/splunk-validated-architectures/splunk-platform-indexing-and-search)

## Lantern / Splunk Success Framework

- [Designing a scalable architecture](https://lantern.splunk.com/Splunk_Success_Framework/Mitigate_Risk/Guarding_against_impact_to_revenue/Designing_a_scalable_architecture)
- [Indexing and search architecture](https://lantern.splunk.com/Splunk_Success_Framework/Platform_Management/Indexing_and_search_architecture)
- [Platform capacity considerations](https://lantern.splunk.com/Splunk_Success_Framework/Platform_Management/Platform_capacity_considerations)
- [Setting up a lab environment](https://lantern.splunk.com/Splunk_Success_Framework/Platform_Management/Setting_up_a_lab_environment)

## Performance (guidance only — not auto-sizing)

- [Summary of performance recommendations](https://help.splunk.com/en/splunk-enterprise/get-started/deployment-capacity-manual/10.2/performance-reference/summary-of-performance-recommendations) — ingest and concurrent search bands; defer production sizing to PS / capacity planning.

## Splunk Platform Automator (SPA)

- [configuration_description.yml](examples/configuration_description.yml) — all config keys
- [Splunk Config Guided Setup](docs/Splunk_Config_Guided_Setup.md) — human-readable mirror of this skill
- [Ansible-Terraform AWS Integration](docs/Ansible_Terraform_AWS_Integration.md) — provision and deploy on AWS
- [App Deployment](docs/App_Deployment.md) — Splunkbase credentials and app blocks
- [App Deployment Guide](docs/App_Deployment_Guide.md) — deep app customization (out of scope for basic app phase)

## Post-deploy reminders (handoff only)

- **Lab:** success = config deploys and cluster forms; not production capacity proof.
- **Production-like:** plan load/DR tests; enable Monitoring Console when `monitoring_console` role is present.
- **Ongoing:** monitor scaling indicators (indexer throughput, search queues, forwarder health).
