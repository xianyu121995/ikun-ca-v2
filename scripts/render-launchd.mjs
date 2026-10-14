import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';

// Render ONLY. This script never installs jobs or calls launchctl.
const [release, nodeBin, configDirectory, logDirectory] = process.argv.slice(2);
if (![release, nodeBin, configDirectory, logDirectory].every(path => path && isAbsolute(path))) {
  throw new Error('Usage: node scripts/render-launchd.mjs ABS_RELEASE ABS_NODE ABS_CONFIG_DIR ABS_LOG_DIR');
}
if (!existsSync(join(release, 'scripts/service.mjs')) || !existsSync(nodeBin) || !['website', 'hunter', 'tracking'].every(name => existsSync(join(configDirectory, `${name}.env`)))) {
  throw new Error('Release, Node binary and three service env files must exist before rendering');
}
const escape = value => value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&apos;');
const output = resolve('var/deploy/launchd');
mkdirSync(output, { recursive: true, mode: 0o700 });
for (const service of ['website', 'hunter', 'tracking']) {
  const envFile = join(configDirectory, `${service}.env`);
  const label = `ca.ikun.v2.${service}`;
  const args = [nodeBin, join(release, 'scripts/service.mjs'), service, 'start'];
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>${label}</string>
<key>ProgramArguments</key><array>${args.map(arg => `<string>${escape(arg)}</string>`).join('')}</array>
<key>WorkingDirectory</key><string>${escape(release)}</string>
<key>EnvironmentVariables</key><dict>
<key>IKUN_ENV_FILE</key><string>${escape(envFile)}</string>
<key>IKUN_ENV</key><string>production</string>
<key>NODE_ENV</key><string>production</string>
<key>NEXT_TELEMETRY_DISABLED</key><string>1</string>
</dict>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ThrottleInterval</key><integer>30</integer>
<key>ExitTimeOut</key><integer>15</integer>
<key>ProcessType</key><string>Background</string>
<key>Umask</key><integer>63</integer>
<key>StandardOutPath</key><string>${escape(join(logDirectory, `${service}.log`))}</string>
<key>StandardErrorPath</key><string>${escape(join(logDirectory, `${service}.error.log`))}</string>
</dict></plist>\n`;
  writeFileSync(join(output, `${label}.plist`), xml, { mode: 0o600 });
}
process.stdout.write(`Rendered three launchd plists in ${output}; not installed\n`);
