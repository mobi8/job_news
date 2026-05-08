const { spawn, execFileSync } = require('child_process');
const path = require('path');

const profileDir = path.resolve(process.env.LINKEDIN_POSTS_PROFILE_DIR || 'outputs/linkedin-post-profile');
const port = process.env.LINKEDIN_CDP_PORT || '9223';
const loginUrl = 'https://www.linkedin.com/login';

function chromeExecutable() {
  if (process.env.CHROME_BIN) return process.env.CHROME_BIN;
  if (process.platform === 'darwin') {
    return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  }
  return 'google-chrome';
}

function killProfileChrome() {
  try {
    execFileSync('pkill', ['-f', `--user-data-dir=${profileDir}`], { stdio: 'ignore' });
  } catch {
    // No matching Chrome process.
  }
}

function openSystemChrome() {
  killProfileChrome();
  const chrome = chromeExecutable();
  const args = [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--no-first-run',
    '--new-window',
    loginUrl,
  ];
  return spawn(chrome, args, { stdio: 'ignore', detached: true }).unref();
}

console.log(`Opening regular Chrome with profile: ${profileDir}`);
console.log(`CDP port: ${port}`);
console.log('LinkedIn에 직접 로그인하세요. 로그인 완료 후 Chrome을 닫지 말고 이 터미널에서 Enter를 누르세요.');
console.log('이후 스크래퍼가 같은 Chrome 세션에 붙어서 바로 수집합니다.');

openSystemChrome();
process.stdin.resume();
process.stdin.on('data', () => process.exit(0));
