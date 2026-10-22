// Runs ONB-01 Code nodes in sequence with mocked n8n helpers and fake API responses.
const fs = require('fs');
const [wfPath, eventPath] = process.argv.slice(2);
const wf = JSON.parse(fs.readFileSync(wfPath, 'utf8'));
const event = JSON.parse(fs.readFileSync(eventPath, 'utf8'));
const codeOf = name => wf.nodes.find(n => n.name === name).parameters.jsCode;

const outputs = {};
const $now = { toFormat: () => '251022-093015', toISO: () => '2025-10-22T09:30:15Z' };
const $ = name => {
  if (!(name in outputs)) return { isExecuted: false, first() { throw new Error('not executed: ' + name); } };
  return { isExecuted: true, first: () => ({ json: outputs[name] }) };
};
const run = (name, input) => {
  const fn = new Function('$input', '$', '$now', codeOf(name));
  const res = fn({ first: () => ({ json: input }), all: () => [{ json: input }] }, $, $now);
  outputs[name] = res[0]?.json;
  return res;
};

run('Config', event);
const cfg = outputs['Config'].config;
cfg.clickup_custom_fields.contact_email = 'fld_email';
cfg.clickup_custom_fields.paid_at = 'fld_paid';
run('Normalize Client', outputs['Config']);
console.log('Normalize Client:', outputs['Normalize Client']);

run('Prepare Provisioning', { id: '86abc123' });
console.log('channel:', outputs['Prepare Provisioning'].slack_channel_name);
console.log('custom fields:', run('Build Custom Fields', outputs['Prepare Provisioning']).map(i => i.json));

// Scenario: channel created, welcome posted, email failed
outputs['Slack: Create Channel'] = { ok: true, channel: { id: 'C0123' } };
outputs['Slack: Welcome Message'] = { ok: true };
run('Slack Result', {});
console.log('Slack Result:', outputs['Slack Result']);
run('Build Registry Update', { error: { message: 'Gmail quota exceeded' } });
console.log('Registry update:', outputs['Build Registry Update']);
run('Build Telegram Message', {});
console.log('--- Telegram ---\n' + outputs['Build Telegram Message'].text);
