# Basic apps questionnaire

**No Splunkbase catalog search** — user supplies `app_id` and folder `name` from Splunkbase or copies from examples.

Deep customization: [docs/App_Deployment_Guide.md](docs/App_Deployment_Guide.md).

## 1. Deploy apps?

If no → omit `splunk_app_deployment` entirely.

## 2. Credentials

Prefer environment variables on controller:

- `SPLUNKBASE_USERNAME`
- `SPLUNKBASE_PASSWORD`

See [docs/App_Deployment.md](docs/App_Deployment.md). Optional vault in config.

## 3. App sources

- `splunkbase` — requires credentials and `app_id`
- `local` — `path` to tarball/spl on controller software dir

## 4. Target roles

`target_roles`: `search_head`, `indexer`, `universal_forwarder`, `heavy_forwarder` (maps to deployer/CM/DS/direct per SPA).

## 5. Premium ITSI?

If yes:

- Main app: `name`, `source: splunkbase`, `app_id: 1841`, `premium_app: itsi`
- Licenses: `Splunk_Enterprise.lic` + `Splunk_ITSI.lic` in `splunk_defaults.splunk_license_file`
- **Java 21 max** on SH/SHC via `os.packages` — see [aws-os-matrix.md](aws-os-matrix.md)
- Reference: `examples/single_node_itsi.yml` (after Java 21 correction)

## 6. ITSI content packs?

- Bundle CP (`itsi_content_pack: true` + `content_pack_apps:`) vs single CP app
- **Folder `name` must match on-disk app name** inside the spl/tgz
- Copy `app_id` lists from examples; do not invent IDs

## 7. Other Splunkbase apps

Per app: `name` (folder name), `app_id`, optional `version: latest`, `target_roles`.

## 8. Local org apps

`source: local`, path under software directory.

## Minimal block sketch

```yaml
splunk_app_deployment:
  splunkbase_username: "{{ lookup('env', 'SPLUNKBASE_USERNAME') }}"
  splunkbase_password: "{{ lookup('env', 'SPLUNKBASE_PASSWORD') }}"
  apps:
    - name: "Splunk IT Service Intelligence"
      source: splunkbase
      app_id: 1841
      premium_app: itsi
      target_roles:
        - search_head
```

## Out of scope

- ES full prerequisite matrix
- Splunkbase search CLI (future)
- Custom `run_playbook` graphs unless user explicitly needs them
