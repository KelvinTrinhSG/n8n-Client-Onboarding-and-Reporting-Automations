// Run inside the n8n container: validates every node's parameters against n8n's own Zod schemas.
const fs = require('fs');
const sdk = '/usr/local/lib/node_modules/n8n/node_modules/@n8n/workflow-sdk/dist/validation/node-parameter-schema/schema-validator.js';
const v = require(sdk);
v.setSchemaBaseDirs(['/usr/local/lib/node_modules/n8n/node_modules/n8n-nodes-base/dist/node-definitions']);

const dir = '/home/node/workflows';
let bad = 0;
for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.json'))) {
  const wf = JSON.parse(fs.readFileSync(`${dir}/${f}`, 'utf8'));
  console.log(`== ${f}`);
  for (const n of wf.nodes) {
    const hasSchema = !!v.loadSchema(n.type, n.typeVersion);
    const r = v.validateNodeConfig(n.type, n.typeVersion, { parameters: n.parameters });
    const tag = !hasSchema ? 'NO-SCHEMA' : r.valid ? 'ok' : 'INVALID';
    if (tag === 'INVALID') bad++;
    console.log(`  [${tag}] ${n.name} (${n.type}@${n.typeVersion})`);
    if (!r.valid) r.errors.forEach(e => console.log('       - ' + (e.message || JSON.stringify(e))));
  }
}
process.exit(bad ? 1 : 0);
