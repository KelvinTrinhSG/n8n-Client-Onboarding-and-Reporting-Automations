// Validates n8n workflow JSON: JS syntax of Code nodes + connection targets.
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
let failed = false;

for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.json'))) {
  const wf = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
  const names = new Set(wf.nodes.map(n => n.name));
  const problems = [];

  for (const n of wf.nodes) {
    if (n.type === 'n8n-nodes-base.code') {
      try { new Function('$input', '$', '$now', `return (async () => {\n${n.parameters.jsCode}\n})`); }
      catch (e) { problems.push(`Code "${n.name}": ${e.message}`); }
    }
    // Referenced nodes in expressions/code must exist
    const text = JSON.stringify(n.parameters);
    for (const m of text.matchAll(/\$\(\\?'([^'\\]+)\\?'\)/g)) {
      if (!names.has(m[1])) problems.push(`"${n.name}" references missing node "${m[1]}"`);
    }
  }
  for (const [src, c] of Object.entries(wf.connections)) {
    if (!names.has(src)) problems.push(`connection source missing: ${src}`);
    for (const out of c.main) for (const t of out) if (!names.has(t.node)) problems.push(`connection target missing: ${t.node}`);
  }
  const connected = new Set(Object.keys(wf.connections));
  Object.values(wf.connections).forEach(c => c.main.flat().forEach(t => connected.add(t.node)));
  for (const n of wf.nodes) {
    if (n.type !== 'n8n-nodes-base.stickyNote' && !connected.has(n.name) && wf.nodes.length > 1)
      problems.push(`node not connected: ${n.name}`);
  }

  console.log(`${f}: ${wf.nodes.length} nodes, ${problems.length ? 'PROBLEMS' : 'OK'}`);
  problems.forEach(p => console.log('   - ' + p));
  if (problems.length) failed = true;
}
process.exit(failed ? 1 : 0);
