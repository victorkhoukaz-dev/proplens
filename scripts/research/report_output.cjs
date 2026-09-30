// Output organization only; calculations and source labels remain unchanged.
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..', '..');
const dataPath = relative => path.join(root, relative);

function emit(payload, kind, season, week, cumulative) {
  const content = JSON.stringify(payload, null, 2);
  if (process.argv.includes('--save')) {
    const stamp = new Date().toISOString().replace(/[-:.]/g, '');
    const scope = `${cumulative ? 'through-week' : 'week'}-${String(week).padStart(2, '0')}`;
    const directory = path.join(root, 'research', String(season), 'betting-process', 'reports', `${scope}_${kind}_${stamp}`);
    fs.mkdirSync(directory, { recursive: true });
    const output = path.join(directory, 'audit.json');
    fs.writeFileSync(output, content + '\n', { flag: 'wx' });
    console.error(`Saved read-only calculation: ${output}`);
  }
  console.log(content);
}

module.exports = { dataPath, emit };
