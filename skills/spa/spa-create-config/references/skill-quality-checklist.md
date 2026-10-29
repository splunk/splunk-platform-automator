# Skill quality checklist

- [ ] `name` matches folder `spa-create-config`
- [ ] Description third person with trigger terms
- [ ] SKILL.md under 500 lines; details in `references/`
- [ ] When to Use / When NOT to Use present
- [ ] Mode (`plan` vs `write`) asked at the gate after the minimum requirements; plan mode skips YAML until approval
- [ ] Step 0 and phase exit criteria followed
- [ ] `bin/*` invoked from project root
- [ ] Secrets: Splunkbase and AWS credential env values never shown in chat or terminal output
- [ ] Incremental add uses `spa --agent config search` then `spa --agent config explain`, then `spa --agent config set`, `spa --agent config add`, or [spa-apps](../../spa-apps/SKILL.md), followed by `spa --agent validate`
